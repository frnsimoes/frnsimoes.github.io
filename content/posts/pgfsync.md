+++
date = 2026-07-18
title = "The lock around WAL flush"
labels = ["draft"]
+++

A slow-storage wait event is ambiguous: the queue can form before the slow operation or after it. If the slow part happens inside a lock, one slow IO cascades into thousands of stuck backends. If it happens outside, though, the same slowness stays contained. This is the story of why 1193 backends piled up behind a WAL append on a database that barely writes, while 194 backends doing reads stayed fine.

Once I had an interesting Postgres IO degradation event - the bottleneck wasn't sequential scans. After a few hours the storage burst balance was exhausted, connections jumped from 200 (baseline) to a few thousand, and checkpoint lag spiked to hours.

At the same time, Postgres hit the antiwraparound threshold of 200M and autovacuum was triggered across databases with old frozen XIDs.

```
wait_event_type |     wait_event      | count
-----------------+---------------------+-------
 LWLock          | WALWrite            |  1193
 IO              | DataFileRead        |   194
 IO              | DataFileWrite       |     4
 Lock            | frozenid            |     2
 IO              | WalSync             |     1
 ```


This time I was surprised. My first guess was: Oh, ok, probably another sequential scan issue. But that wasn't it. Look at WALWrite vs DataFileRead.

Why are backend processes being locked behind a simple WAL write? Before I looked at pg_stats, my first guess was that autovacuum was the culprit. But only two processes were locked on frozenid - that wasn't it. WALWrite is not an IO wait, it's a lock event. Processes were waiting on each other.

I remember I thought: but why? A WAL record is small, and writing to it is an append. Well, today I had the chance to dig deeper by reading [xlog.c](https://github.com/postgres/postgres/blob/master/src/backend/access/transam/xlog.c#L2325) in the source code. 

### The insert path

The first thing I found was the insert side. 

```
* Inserting to WAL is protected by a small fixed number of WAL insertion
* locks. To insert to the WAL, you must hold one of the locks - it doesn't
* matter which one.
```

We have 8 `NUM_XLOGINSERT_LOCKS`. The insert itself is two steps:

```
* 1. Reserve the right amount of space from the WAL. The current head of
*    reserved space is kept in Insert->CurrBytePos, and is protected by
*    insertpos_lck.
*
* 2. Copy the record to the reserved WAL space. This involves finding the
*    correct WAL buffer containing the reserved space, and copying the
*    record in place. This can be done concurrently in multiple processes.
```

Step 1 is serialized, and they say so in `ReserveXLogInsertLocation`:

```
* This is the performance critical part of XLogInsert that must be serialized
* across backends. The rest can happen mostly in parallel. Try to keep this
* section as short as possible, insertpos_lck can be heavily contended on a
* busy system.
```

Under the spinlock:


```
SpinLockAcquire(&Insert->insertpos_lck);

startbytepos = Insert->CurrBytePos;
endbytepos = startbytepos + size;
prevbytepos = Insert->PrevBytePos;
Insert->CurrBytePos = endbytepos;
Insert->PrevBytePos = startbytepos;

SpinLockRelease(&Insert->insertpos_lck);
```

That's only three reads and two writes. Not that much work. If this was the problem, I would've seen `LWLock:WALInsertLock`. But I didn't. 

### The flush path

The flush path is more interesting:

```
* WALWriteLock: must be held to write WAL buffers to disk (XLogWrite or
* XLogFlush).
(...)
* info_lck is only held long enough to read/update the protected variables,
* so it's a plain spinlock. The other locks are held longer (potentially
* over I/O operations), so we use LWLocks for them.
```

So flush is 1 lock, exclusive. Very different from the 8 locks of the insert path. Since there's only one WAL stream and one device, this is where successful inserts fall into. It makes sense.

XLogWrite does a pg_pwrite under that lock. The write path often only has to copy WAL data into the kernel/page cache, although it can also stall if the kernel/device is already under pressure. After that, we get fsync - issue_xlog_fsync, which goes through the block layer, the driver, across the network. The durable wait is usually the dangerous part. This also makes sense.

Out of all those 1193 backends, most were not doing I/O themselves. They were sleeping while waiting for the backend holding WALWriteLock to finish.

But shouldn't the kernel have handled this issue? Storage saturation doesn't signal anything to the kernel because there were no errors - things were waiting on a lock, that's it. Once storage saturated, requests beyond the baseline were effectively throttled, increasing fsync latency. From the kernel's point of view the device got slower, and the fsync inside the critical section takes longer, the lock is held longer, and 1193 backends wait longer for the lock.

### What happens inside a DataFileRead

The answer is at [bufmgr.c](https://github.com/postgres/postgres/blob/master/src/backend/storage/buffer/bufmgr.c) - a read looks up the page in the shared buffers first, and that lookup is partitioned. Take a look at BufferAlloc:

```
LWLockAcquire(newPartitionLock, LW_SHARED);
existing_buf_id = BufTableLookup(&newTag, newHash);
if (existing_buf_id >= 0)
{
    BufferDesc *buf;
    bool        valid;

    buf = GetBufferDescriptor(existing_buf_id);
    valid = PinBuffer(buf, strategy, false);

    /* Can release the mapping lock as soon as we've pinned it */
    LWLockRelease(newPartitionLock);
    ...
    return buf;
}

/*
 * Didn't find it in the buffer pool.  We'll have to initialize a new
 * buffer.  Remember to unlock the mapping lock while doing the work.
 */
LWLockRelease(newPartitionLock);
```

"Pin" here means: mark this buffer as in use, so nothing else recycles its slot while you're reading it. It's a counter that goes up when reading the page, and down when the read is done.

The read lock in this case is LW_SHARED - it's not exclusive like the WAL flush lock. The most important difference though is when the read lock gets released: right after the lookup, on both paths. BufferAlloc finds the buffer, drops the lock, and returns without touching disk while holding the lock. This is the meaning of the comment on the miss path: unlock while doing the work, the read comes after, outside this function.

The distinction: WAL holds one exclusive lock across the fsync, read drops its lock before IO happens. The slow part - waiting on the device per se - is inside the lock for WAL and outside it for reads.

This is why the 194 DataFileRead didn't pile up. Each issued read waited on its own IO, and there were no locks between reads. DataFileRead grows with how many IOs are in flight. WALWrite grows with how long one backend holds the flush lock, even though the device beneath is the same for both.

(Reads do serialize in one case: two backends wanting the same page that isn't loaded into shared buffers yet - in this case, one reads it, the other waits. But that's one page at one instant. Backends scanning different pages never hit it.)


### Why not just split the flush lock?

If reads scale by partitioning the buffer table, why not do the same to the WAL flush? I searched. Someone tried exactly this in a [2016 pgsql-hackers thread](https://www.postgresql.org/message-id/CAGz5QCLUZKRezjnhu2VtU5K-1-JGeGf+aJk8iqvF80z4QNywAw@mail.gmail.com). The idea was to move the flush out of WALWriteLock and into a separate WALFlushLock, so an OS write could happen while a fsync was still in progress.

But it made things worse. Throughput dropped 10 to 12% because the contention split and grew. In their own words:

```
But, we didn't see any performance improvements, rather it decreased by 10%-12%.
Hence to measure the wait events, we performed a run for 30 minutes with 64 clients.

HEAD
------------------------
48642 LWLockNamed | WALWriteLock

With Patch
----------------------------------
31889 LWLockNamed | WALFlushLock
25212 LWLockNamed | WALWriteLock

The contention on WAL Write Lock was reduced, but together with WAL Flush
lock, the total contention got increased.

...

Due to reduced contention on WAL Write Lock, lot of backends are going for
small os writes, sometimes on same 8KB page, i.e., write calls are not
properly accumulated.
```

There were two reasons: the cost for lock acquire/release was now double, and splitting broke the batching - "when fsync is going, we are not able to accumulate sufficient data for the next fsync". The single fsync model is useful because it covers many commits (group commit). Splitting fsync means we now have to deal with batching in another way.

The reason reads and WAL aren't symmetric is: different pages are independent, so there's no need to have only one lock reading different pages. WAL records are different - they are ordered (one log and stream). Its purpose is to be replayed in sequence, so you can't just shard the flush without paying the ordering back somewhere.

Worth a caution, though: seeing WALWrite in the wait events doesn't prove the lock itself is the ceiling. Andres Freund, on a later report of the same contention, [doubted the lock was the prime issue](https://www.mail-archive.com/pgsql-hackers@postgresql.org/msg317461.html) and noted Postgres scaling further without it dominating. In my case the lock was a symptom - the device underneath was saturated - not the root cause. 

---

### Things I still don't know

There are things I still don't know: I don't know how much autovacuum impacted IO exhaustion - the storage-balance metric was measured at the instance level, so it included vacuum reads, query reads, checkpoint writes, and WAL activity. Peak was most writes, which points away from the vacuum reads. But the vacuum *was* writing too since it generates WAL.


I also don't have a fsync number because I didn't check pg_stat_wal during the incident, which is annoying. 1193 is an observed queue length, not a direct fsync-latency measurement.

We can use Little's Law in order to make sense of the numbers: queue length = arrival rate * waiting time.

These numbers are illustrative, not a claim that I measured 5000 commits/s in this incident:

- 5000 flush/commit arrivals per second * 1ms service time = 5 backends
- 5000 flush/commit arrivals per second * 240ms service time = 1200 backends

The point is not the exact 240ms. The point is that once fsync/service time moves from single-digit milliseconds to hundreds of milliseconds, the queue can become four digits very quickly. The missing variables are the flush arrival rate and ms_per_sync from pg_stat_wal.

### What this was really about

I learned a lot. LWLock:WALWrite is not really "oh boy, there are lots of wal writes right now". It represents something more threatening: there's a lock, something is holding that lock, everyone else who is waiting on the line is sleeping. There's only one flush path, and once a backend is holding that lock across a slow flush, the others cannot progress until it completes. This is threatening because of how fast service time scales up and the queue fills. What happened during the incident is a clear example of this.

---
*Operational values have been rounded and identifying details omitted; the technical behavior is unchanged.*
