+++
date = 2026-07-18
title = "1193 backends on WALWrite, and lore"
labels = ["post"]
+++

An interesting wait event table I found in production:

```
wait_event_type | wait_event    | count
----------------+---------------+-------
LWLock          | WALWrite      |  1193
IO              | DataFileRead  |   194
IO              | DataFileWrite |     4
Lock            | frozenid      |     2
IO              | WalSync       |     1
```

1193 backends were waiting on WALWrite. This was a nasty production incident - we ran out of IOPS first, then an anti-wraparound autovacuum started running, which made everything worse: checkpoint lag and connections went through the roof. But the thing that really impacted customers while the incident was going on was a specific endpoint that inserts data into this database. A few weeks after the incident, I took a look at that table again. The first thing I thought: why does WAL need a lock? Later, I found an interesting comment in xlog.c:

```
* WALWriteLock: must be held to write WAL buffers to disk (XLogWrite or
* XLogFlush).
(...)
* info_lck is only held long enough to read/update the protected variables,
* so it's a plain spinlock. The other locks are held longer (potentially
* over I/O operations), so we use LWLocks for them.
```

XLogWrite does a pg_pwrite while holding the lock, then calls issue_xlog_fsync. The [docs](https://www.postgresql.org/docs/current/wal-configuration.html) treat these as two separate costs: with track_wal_io_timing `on` they show up as write_time and fsync_time in pg_stat_io.

Now let's take a look at the WalSync row. This is the process inside fsync.

WAL is one sequential stream and there is a single flush pointer, so a flush to 150 has persisted everything before it. Most of those 1193 backends don't need a flush of their own. They are waiting for the current one to finish so they can check whether it already covered them. That's [what the lock is doing](https://github.com/postgres/postgres/blob/512d3e8919b649d36a6f246c657c8b8df7536e8a/src/backend/storage/lmgr/lwlock.c#L1364). Postgres has no group commit *queue*. 

So LWLock/WALWrite has two meanings: "queued to flush" and "waiting to find out I don't need to flush". Andres Freund made roughly this point on a [later report of the same symptom](https://www.mail-archive.com/pgsql-hackers@postgresql.org/msg317461.html).

What about splitting it?

Someone tried the split in a [2016 pgsql-hackers thread](https://www.postgresql.org/message-id/CAGz5QCLUZKRezjnhu2VtU5K-1-JGeGf+aJk8iqvF80z4QNywAw@mail.gmail.com). The idea was to move the flush out of WALWriteLock and into a separate WALFlushLock, so an OS write could happen while an fsync was still in progress.

But it made things worse. Throughput dropped 10 to 12%. In their own words:

> But, we didn't see any performance improvements, rather it decreased by 10%-12%.
> Hence to measure the wait events, we performed a run for 30 minutes with 64 clients.

It removed the contention and the batching at the same time.

Two reasons for this: lock acquire/release cost and, more interestingly:

> Due to reduced contention on WAL Write Lock, lot of backends are going for small os writes,
> sometimes on same 8KB page, i.e., write calls are not properly accumulated.

## Lore

Postgres once had a real group commit implementation.

[In August 2011](https://postgresql.org/message-id/CA%2BU5nM%2B3f4yOrR39MqAMXQSsxn28JXzyU8AsL9O8qNL%2B8NANtg%40mail.gmail.com), Simon Riggs proposes reworking WAL writing. 

[In January 2012](https://www.postgresql.org/message-id/CAEYLb_V5Q8Zdjnkb4%2B30_dpD3NrgfoXhEurney3HsrCQsyDLWw%40mail.gmail.com), Peter Geoghegan posts a rewrite of that patch. The benchmarks looked nice.

[Ten days later](https://postgresql.org/message-id/4F1FB914.2060003%40enterprisedb.com), Heikki Linnakangas asks what part of the patch is actually producing the benefit. His conclusion is that the sorted queue is not important because flush requests arrive in nearly the right order anyway. He then writes his own patch that deletes the queue entirely and adds one lwlock mode.

[Heikki's version gets committed](https://postgresql.org/message-id/E1RrsdP-0005K7-PI%40gemulon.postgresql.org) on 2012-01-30, as [Make group commit more effective](https://git.postgresql.org/gitweb/?p=postgresql.git;a=commitdiff;h=9b38d46d9f5517dab67dda1dd0459683fc9cda9f).

Everything above landed in Postgres 9.2. But what I found interesting was noticing the time sequence of those messages: Simon proposes. Heikki commits at 02:55 PM UTC. At 08:04 PM he emails the thread asking Simon what approach he is working on. At 11:35 PM [Simon answers](https://www.postgresql.org/message-id/CA%2BU5nM%2BYj7scbELbftqPi%3DZn1Q6SDM%2BPDgM0npkiRRrc_tS-xg%40mail.gmail.com): 

> I've had a few days leave at end of last week, so no time to fully
> discuss the next steps with the patch. That's why you were requested
> not to commit anything.

And that is still the approach used today.

---
A note on the incident, since a few people asked: there wasn't much we could do. This is on AWS RDS. We provisioned 12k IOPS on EBS, but the instance type we were using, an m6g.large, has its own limit, and once the EBSIOBalance% drained we were down to the baseline (~4k). That was a surprise, I didn't know the instance itself capped the IOPS even though we provisioned more than that. One of those AWS surprises, I guess.
