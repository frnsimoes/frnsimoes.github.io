+++
date = 2026-02-08
title = "Between select and disk"
labels = ["favorite"]
subjects = ["database", "production"]
+++ 

We had a Postgres incident this week. Heroku timeouts, multiple queries running for 30+ minutes, and the IOPS pinned at the provisioned limit.

I knew I needed a better index, but I wanted to understand what "reading from disk" actually means first. How many layers of caching sit between a SELECT and the storage device?

Three.

First: shared buffers, Postgres' own cache living in the process memory. If the page is there, we need no system call - just a memory read. Ours was set to 4GB.

Second: the OS page cache. If Postgres doesn't have the page, it calls read(2), and now we're in the kernel. The kernel keeps its own cache of disk blocks, and if the block is there it returns it immediately. No I/O happened - from Postgres' perspective it was a miss, but from the OS perspective it was still a memory read.

These two compete for the same physical RAM. When you bump shared buffers from 4GB to 16GB you take 12GB from the page cache. The page cache benefits everything, not just what Postgres explicitly requested, so there's a point where growing shared buffers actually makes things worse.

Third: disk. If neither cache has the page, the kernel sends an I/O request to the device. On Heroku, that's AWS EBS. This is what counts as one IOPS.

Our limit was 3000 provisioned, with burst credits for temporary spikes. Logs showed reads hitting 3668 - the burst credits were keeping us alive, but when they run out you're hard-capped.

Our shared buffer hit ratio was 78%, but that number lies if you don't understand the layers. `pg_statio_user_tables` counts shared buffer hits vs shared buffer misses, and a "miss" just means Postgres asked the OS - the OS might still serve it from page cache without touching disk. So 78% is the Postgres-level hit ratio, not the actual "went to disk" ratio. The real disk read ratio is lower, except during overnight schedulers when the working set blew past both caches and actual disk reads spiked hard.

The table at the center of this was a big one: 46.7GB heap plus TOAST, 28.1GB in indexes, peaks of 4000 updates per minute, and large JSONB columns.

Two query patterns were doing most of the damage, and both followed the same pathology: filter by account_id using an index, then apply JSONB filters after fetching the rows from disk.

Here's one:

    Index Scan using idx_account_id on leads
      Filter: ((some_column IS NULL) AND (jsonb_condition))
      Index Cond: (account_id = 4939)
      Rows Removed by Filter: 39811
      Buffers: shared hit=10871 read=27841 dirtied=3
      I/O Timings: shared/local read=13838.335

39,811 rows fetched from disk, all discarded by the filter. Zero rows returned.

27,841 block reads x 8KB = 217MB of disk reads in 14 seconds. That's roughly 1,989 IOPS from a single query that returned nothing.

The second pattern was similar: 12,071 rows fetched and discarded, 107MB from disk, around 1,944 IOPS. Also zero rows returned. Two of these running at the same time is enough to blow past 3000 IOPS.

The index was a plain B-tree on account_id and nothing else. It says "account 4939 has 39,811 rows, here's where they are on disk," but it knows nothing about the JSONB columns. That information only exists in the heap.

So Postgres fetches all 39,811 rows, reads them, checks the filters, and throws away everything. And those heap fetches are essentially random - the rows for a given account_id are scattered across the table because Postgres doesn't update tuples in place. It marks the old one dead and inserts a new version somewhere else. 4000 updates per minute means rows that logically belong together end up physically spread across thousands of pages in a 46GB table. Every fetch is a different page, and every page is a potential disk read.

The index tells Postgres where the rows are. "Where" just happens to be everywhere.

Reading the index is also I/O, by the way - the B-tree lives on disk too. So the access pattern is: read index pages, get a list of row locations, then read heap pages at those locations. Two rounds.

The fix is a GIN index on the JSONB column so Postgres can evaluate those filters inside the index scan without touching the heap. A partial index for the NULL condition would help too.
