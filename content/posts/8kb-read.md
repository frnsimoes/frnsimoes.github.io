+++
date = 2026-06-12
title = "An experiment on Postgres read latency"
labels = ["post"] 
+++

We had an IOPS incident a few months back. I couldn't observe what was happening because EBS hides the storage implementation details - I couldn't tell whether Postgres was serving pages from shared_buffers, linux page cache or physical storage. Since those layers have very different latencies, I wanted to measure each of them independently. So I experimented in a more controlled environment: how a shared buffer hit, an OS page cache hit, and a disk hit differ.

The setup is pretty simple: a debian box I keep at home. I'm running Postgres 17 in Docker, `shared_buffers = 16MB`, `track_io_timing = on`. The storage is a local NVMe SSD, ext4. I built a table deliberately bigger than the cache:

```
postgres=# SELECT pg_size_pretty(pg_relation_size('leads')), pg_relation_size('leads')/8192;
 pg_size_pretty | ?column?
----------------+----------
 115 MB         |    14706
```

The point of creating a table way bigger than shared_buffers is to guarantee that a full read cannot fit in Postgres's own cache.

The table model: there's an `id`, an `user_id`, and a fat jsonb payload. There is only a plain B-tree index on `user_id`. The two worst queries in the incident did the same thing: filter by `user_id` with the index, then apply a second filter on a non-indexed column after fetching the rows. This is what I'm reproducing here. For user 42:

```
postgres=# SELECT count(*), count(DISTINCT (ctid::text::point)[0]) AS heap_pages
postgres-#   FROM leads WHERE user_id = 42;
 count | heap_pages
-------+------------
   500 |        500
```

Ok, so we have 500 rows scattered across 500 distinct heap pages. To read user 42, Postgres reads the index to learn the row locations, then fetches 500 separate pages from the heap. The query I run adds a filter on `payload`, which the index cannot evaluate, so all 500 rows are fetched and then discarded.

```
Index Scan using idx_user_id on leads
  Index Cond: (user_id = 42)
  Filter: (payload ~~ '%zzzz%'::text)
  Rows Removed by Filter: 500
```

Yes, we got 4 MB of I/O for absolutely nothing (`rows removed by filter`). This is the setup, now the plan is to run the same query in three cache states and read the `Buffers` line each time and see what happens.

**Shared Buffers**

While the pages are still warm, let's run the query one more time:

```
Index Scan using idx_user_id on leads (actual time=0.534..0.534 rows=0)
  Buffers: shared hit=504
Execution Time: 0.569 ms
```

`shared hit=504` - every page was already in the process memory, so there was no system call at all. `pg_buffercache` confirms they are resident:

```
postgres=# SELECT c.relname, count(*) FROM pg_buffercache b
postgres-#   JOIN pg_class c ON b.relfilenode = pg_relation_filenode(c.oid)
postgres-#   WHERE c.relname IN ('leads','idx_user_id') GROUP BY 1;
    relname     | count
----------------+-------
 leads          |   500
 idx_user_id    |   5
```

0.57 ms. Good.

**OS page cache**

Now let's drop the pages from shared buffers (a simple restart will do because shared buffers is process memory. This will not remove the OS page cache, for obvious reasons). With cold shared buffers and warm OS cache:

```
Index Scan using idx_user_id on leads (actual time=2.292..2.293 rows=0)
  Buffers: shared read=504
  I/O Timings: shared read=2.024
Execution Time: 2.316 ms
```

We got `shared read` instead of the last run's `shared hit`. This means we issued a read(2) syscall. Postgres doesn't know the behavior of the syscall, though, all it knows is that there were 504 misses. The I/O timings: 2.024 for all 504 reads, which is about 4 microseconds per read.

**Disk**

Let's now drop the OS page cache as well, so the read has nowhere to go but the SSD - of course, it could go to the SSD DRAM, but I can confirm my SSD model doesn't have a DRAM. Two things first: restart Postgres to clear its own memory, then `echo 3 > /proc/sys/vm/drop_caches` to clear the OS page cache, and run the same query again.

```
Index Scan using idx_user_id on leads (actual time=39.991..39.991 rows=0)
  Buffers: shared read=504
  I/O Timings: shared read=39.502
Execution Time: 40.276 ms
```

39.5 ms - about 78 microseconds per read, 20 times slower than the page cache.

Let's run `fio` to compare that number against the SSD itself. I'm going to use `psync` so we issue synchronous events, random 8kb reads to comply with the Postgres page size, and `--direct=1` to bypass the page cache. 

```
frn@debian:~$ fio --name=randread --filename=/home/frn/.fio_test --size=1G \
              --bs=8k --rw=randread --direct=1 --ioengine=psync --iodepth=1 \
              --runtime=8 --time_based
...
read: IOPS=13.2k
clat (usec): min=61, avg=75.70, 99.00th=[84]
```

This is consistent with direct random reads from the SSD.

In addition, I also experimented reading the same 500 cold pages in sorted order instead of index order. The cost was 2.8ms. I didn't expect this, but it makes sense since the kernel sees the sequential pattern and [loads the next pages into the page cache](https://kernel-internals.org/io/readahead/) before Postgres asks for them. If pages come in random order, the kernel cannot guess what comes next, so readahead does nothing and every read waits for the NVMe. 

In summary, the cost per 8kb read:

- Shared buffers = memory read, no syscall
- OS page cache = ~4 microseconds
- Local NVMe, old = ~78 microseconds

Well, that's a lot of work just to see numbers popping out, but I'm glad I did it. 
