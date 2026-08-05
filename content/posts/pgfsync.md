+++
date = 2026-07-18
title = "Reads vs writes under pressure"
labels = ["post"]
+++

Take a look at this wait-event table:

```
wait_event_type | wait_event    | count
----------------+---------------+-------
LWLock          | WALWrite      |  1193
IO              | DataFileRead  |   194
IO              | DataFileWrite |     4
Lock            | frozenid      |     2
IO              | WalSync       |     1
```

1193 backends on WALWrite made no sense at all. This was a Postgres whose normal workload barely wrote anything. IOPS had exhausted a few hours earlier, connections had climbed from a few hundred to a few thousand, checkpoints were hours behind, and Postgres also had crossed the anti-wraparound threshold, so autovacuum was working with old frozen XIDs.

Since writes seemed to be bonking the database, I needed to understand why. Postgres was running on the baseline IOPS (~4k at that moment), so any IO operations would wait, but reads and writes do not wait in the same way.

The question now turned from "what's happening?" to "why is the writing queue so much longer?". The kind of question you only answer after an incident, and only at 2am when sleep isn't happening.

I found out one interesting thing xlog.c: Postgres flushes into WAL while holding an info_lck.

```
* WALWriteLock: must be held to write WAL buffers to disk (XLogWrite or
* XLogFlush).
(...)
* info_lck is only held long enough to read/update the protected variables,
* so it's a plain spinlock. The other locks are held longer (potentially
* over I/O operations), so we use LWLocks for them.
```

It's one exclusive lock. It makes sense. 

XLogWrite does a pg_pwrite under that lock. The write path often only has to copy WAL data into the kernel/page cache, although it can also stall if the kernel/device is already under pressure - ta da! After that, we get fsync on issue_xlog_fsync, which goes through the block layer, driver, maybe across the network. 

So it took only one flush in a lock to hold all those 1193 backends. Next question: Shouldn't the kernel have handled this issue? Storage saturation doesn't signal anything to the kernel because there were no errors - things were waiting on a lock, that's it. Once storage saturated, requests beyond the baseline were effectively throttled, increasing fsync latency. From the kernel's point of view the device got slower, and the fsync inside the critical section takes longer, the lock is held longer, and 1193 backends wait longer for the lock.

But since we had so many more reads than writes, why only 194 DataFileRead? The answer is in bufmgr.c:

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

A read looks up the page in the shared buffers first, and that lookup is partitioned.

"Pin" here means: mark this buffer as in use, so nothing else recycles its slot while you are reading it. It's a counter.

The read lock is also a LW_SHARED - which means it's not an exclusive lock like the WAL flush lock. The most important difference though is when the read lock gets released: right after the lookup, on both paths. BufferAlloc finds the buffer, drops the lock, and returns without touching disk while holding the lock. This is the meaning of the comment on the miss path: unlock while doing the work, the read comes after, outside this function. Reads drop the lock *before IO happens*.

DataFileRead grows with how many IOs are in flight, and WALWrite grows with how long one backend holds the flush lock, even though the device beneath is the same for both of them.

So we can have multiple parallel reads (they only serialize if the reads are trying to read the same page), which will be serviced independently. Flushes need to wait in a single line. That's the difference.

Why not just split the flush lock, then?

If reads scale by partitioning the buffer table, why not do the same to the WAL flush? I searched. Someone tried exactly this in a [2016 pgsql-hackers thread](https://www.postgresql.org/message-id/CAGz5QCLUZKRezjnhu2VtU5K-1-JGeGf+aJk8iqvF80z4QNywAw@mail.gmail.com). The idea was to move the flush out of WALWriteLock and into a separate WALFlushLock, so an OS write could happen while a fsync was still in progress.

But it made things worse. Throughput dropped 10 to 12% because the contention split and grew. In their own words:

```
But, we didn't see any performance improvements, rather it decreased by 10%-12%.
Hence to measure the wait events, we performed a run for 30 minutes with 64 clients.

...

Due to reduced contention on WAL Write Lock, lot of backends are going for small os writes,
sometimes on same 8KB page, i.e., write calls are not properly accumulated.
```

There were two reasons: the cost for lock acquire/release was now double, and splitting broke the batching - "when fsync is going, we are not able to accumulate sufficient data for the next fsync". The single fsync model is useful because it covers many commits (group commit). Splitting fsync means we now have to deal with batching in another way.

The reason reads and WAL aren't symmetric is: different pages are independent, so there's no need to have only one lock reading different pages. WAL records are different - they are ordered (one log and stream). Its purpose is to be replayed in sequence, so you can't just shard the flush without paying the ordering back somewhere.

Worth a caution, though: seeing WALWrite in the wait events doesn't prove the lock itself is the ceiling. Andres Freund, on a later report of the same contention, [doubted the lock was the prime issue](https://www.mail-archive.com/pgsql-hackers@postgresql.org/msg317461.html) and noted Postgres scaling further without it dominating. In my case the lock was a symptom - the device underneath was saturated - not the root cause. 

The point of all of this is that WAL-bound writes gets into a serialized queue. Reads are different since they usually release the shared-buffer mapping locks before performing I/O. Reads queue primarily at OS/storage level, not at Postgres level.

