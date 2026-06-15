+++
date = 2026-06-12
title = "Tracing an 8kb Postgres read"
labels = ["post"] 
subjects = ["database", "production"]
+++

A while ago I had an IOPS production incident, which I wrote about [here](/iops). What I want to do in this post, though, is measure what happened. To do this, I need to isolate the problem and place it in a context I fully control. You don't need to read the incident report text to follow this one. Ok. Here is the plan: run the same query three times and measure each run: first with the pages in shared buffers, then with the pages only in the OS page cache, and finally reading everything from disk. After that, I compare the numbers with two disks hidden behind cloud abstractions: the EBS volume from the incident, and a Hetzner server I benchmarked a while ago.

The setup is pretty simple: a debian box I keep at home. I'm running Postgres 17 in Docker, `shared_buffers = 16MB`, `track_io_timing = on`. The storage is a local NVMe SSD, ext4. I built a table deliberately bigger than the cache:

```
postgres=# SELECT pg_size_pretty(pg_relation_size('leads')), pg_relation_size('leads')/8192;
 pg_size_pretty | ?column?
----------------+----------
 115 MB         |    14706
```

The point of creating a table way bigger than shared_buffers is to guarantee that a full read cannot fit in Postgres's own cache.

The table is modeled on the one that broke in production: there's an `id`, an `account_id`, and a fat jsonb payload. There is only a plain B-tree index on `account_id`. The two worst queries in the incident did the same thing: filter by `account_id` with the index, then apply a second filter on a non-indexed column after fetching the rows. This is what I'm reproducing here. For account 42:

```
postgres=# SELECT count(*), count(DISTINCT (ctid::text::point)[0]) AS heap_pages
postgres-#   FROM leads WHERE account_id = 42;
 count | heap_pages
-------+------------
   500 |        500
```

Ok, so we have 500 rows scattered accross 500 distinct heap pages. To read account 42, Postgres reads the index to learn the row locations, then fetches 500 separate pages from the heap. The query I run adds a filter on `payload`, which the index cannot evaluate, so all 500 rows are fetched and then discarded.

```
Index Scan using idx_account_id on leads
  Index Cond: (account_id = 42)
  Filter: (payload ~~ '%zzzz%'::text)
  Rows Removed by Filter: 500
```

Yes, we got 4 MB of I/O for absolutely nothing (`rows removed by filter`). This is the setup, now the plan is to run the same query in three cache states and read the `Buffers` line each time and see what happens.

**Shared Buffers**

Let's run the query a second time, while the pages are still warm:

```
Index Scan using idx_account_id on leads (actual time=0.534..0.534 rows=0)
  Buffers: shared hit=504
Execution Time: 0.569 ms
```

`shared hit=504` - every page was already in the process memory, so there was no system call at all. `pg_buffercache` confirms they are resident:

```
postgres=# SELECT c.relname, count(*) FROM pg_buffercache b
postgres-#   JOIN pg_class c ON b.relfilenode = pg_relation_filenode(c.oid)
postgres-#   WHERE c.relname IN ('leads','idx_account_id') GROUP BY 1;
    relname     | count
----------------+-------
 leads          |   500
 idx_account_id |     5
```

0.57 ms. Good.

**OS page cache**

Now let's drop the pages from shared buffers - restarting wipes it because shared buffers is process memory. This will not wipe the OS page cache, for obvious reasons. With cold shared buffers and warm OS cache:

```
Index Scan using idx_account_id on leads (actual time=2.292..2.293 rows=0)
  Buffers: shared read=504
  I/O Timings: shared read=2.024
Execution Time: 2.316 ms
```

Instead of the `shared hit` we got in the first try, we now get a `shared read`, meaning we had to issue a `read(2)` syscall. Postgres doesn't know the behavior of the syscall. From Postgres's point of view, these were 504 misses: 504 `read(2)` calls. But look at the timing - 2.024 ms for all 504 reads, about 4 microseconds per read. 

We can assume that no disk was touched because [latency numbers are well known](https://gist.github.com/jboner/2841832). But we can also compare the numbers with the next run's numbers.

**Disk**

Now we drop the OS page cache as well, so the read has nowhere to go but the SSD - of course, it could go to the SSD DRAM, but I can confirm my local model doesn't have a DRAM. Two steps: restart Postgres to clear its own memory, then `echo 3 > /proc/sys/vm/drop_caches` to clear the OS page cache, and run the same query again.

```
Index Scan using idx_account_id on leads (actual time=39.991..39.991 rows=0)
  Buffers: shared read=504
  I/O Timings: shared read=39.502
Execution Time: 40.276 ms
```

39.5 ms - about 78 microseconds per read, 20 times slower than the page cache. 

Let's compare that number against the bare metal device with `fio`, random 8kb reads with `--direct=1` to bypass the page cache. 

```
frn@debian:~$ fio --name=randread --filename=/home/frn/.fio_test --size=1G \
              --bs=8k --rw=randread --direct=1 --ioengine=psync --iodepth=1 \
              --runtime=8 --time_based
...
read: IOPS=13.2k
clat (usec): min=61, avg=75.70, 99.00th=[84]
```

76 microseconds per read, Postgres measured 78, so they practically agree. This confirms the cost is the SSD itself.

In addition, I also experimented reading the same 500 cold pages in sorted order instead of index order. The cost was 2.8ms. This surprised me a lot, but [the kernel sees the sequential pattern and loads the next pages into the page cache](https://kernel-internals.org/io/readahead/) before Postgres asks for them. If pages come in random order, the kernel cannot guess what comes next, so readahead does nothing and every read waits for the NVMe. 

And there is still one layer below this. In production the disk was not a local SSD, it was AWS EBS, network-attached. This was the plan that pinned our IOPS:

```
Index Scan using idx_account_id on leads
  Filter: ((some_column IS NULL) AND (jsonb_condition))
  Rows Removed by Filter: 39811
  Buffers: shared hit=10871 read=27841 dirtied=3
  I/O Timings: shared/local read=13838.335
```

There were 27,841 reads the OS could not serve from cache. 13,838 ms of I/O time, about 497 microseconds per read. Lined up, the cost of reading that same 8 KB page is a clean descent. A page in the shared buffers costs a memory read. From the kernel's page cache, the cost climbs to about 4 microseconds. Reads cold from the local NVMe, about 78 microseconds. And in production, fetched from EBS across the network, about 497. Every step down is roughly an order of magnitude: EBS is about 6x slower than the local SSD and 124x slower than the page cache ([at least in the example](https://news.ycombinator.com/item?id=40456780)). 


---

## Another cloud disk

Finally, I want to confirm if this is an EBS problem or a network-attached problem. While writing this post I remembered that a couple of months before, I was choosing a server for a Postgres cluster - a Hetzner CCX33: 8 vCPUs, 32 GB of RAM, 240 GB of NVMe - and I had run `fio` on it. The numbers are worth putting next to the EBS ones.

Random 8 KB reads first, with more pressure than the home test (`--iodepth=32 --numjobs=4`, still `--direct=1`):

```
read: IOPS=325k
clat: p1=668ns, p50=123us, p99=1.3ms
```

325,000 IOPS and a p50 of 123 microseconds - on paper, faster than my NVMe at home. But the p1 is 668 nanoseconds, and the NVMe at home never answered below 61 microseconds: that is the time the flash itself takes. Sub-microsecond is RAM. `--direct=1` skips the VM's page cache, but on a cloud server there is a hypervisor between the VM and the storage, and the hypervisor has a cache of its own. Part of these reads never left the host's RAM, so this test measures caches as much as it measures the disk - the same lesson as the Postgres layers, one level down.

Writes with fsync don't have this problem, because fsync only returns when the data is persisted:

```
root@ubuntu-32gb-hil-1:~$ fio --name=randwrite-fsync --rw=randwrite --bs=8k --fsync=1 \
              --iodepth=32 --numjobs=4 --runtime=120 --ioengine=libaio \
              --direct=1 --group_reporting --time_based --ramp_time=10 \
              --size=20G --filename=/mnt/bench/test.bin
...
write: IOPS=10.2k
clat: p50=12.1ms, p99=16.2ms
```

12 milliseconds for an 8 KB write to become durable. A write is not a read, so the comparison with the numbers above is loose, but the point is the scale. The NVMe at home answers in tens of microseconds. The EBS read took about 500. A durable write here takes 12,000. Whatever runs under that VM, it behaves like the EBS volume, not like my local NVMe. 

