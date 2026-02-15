+++
date = 2026-02-13
title = "What happens inside Postgres when IOPS runs out"
+++ 

In the [previous post](/iops) I wrote about the three cache layers between a SELECT and disk. That post came from a production incident - queries hanging for 35+ minutes, Heroku timeouts, IOPS pinned at 3000. We fixed it. The root cause was bad indexes forcing Postgres to fetch tens of thousands of rows from disk only to discard them. Better indexes, problem solved.

During the incident, the system hit 3000 IOPS and stayed there. It didn't recover on its oown. We had to kill connections manually. But why? What was actually happening inside Postgres that made the situation self-sustaining? I had a wrong mental model for days. This post is about fixing that.

## When read(2) has to wait

When Postgres needs a page that's not in shared buffers and not in the OS page cache, the kernel has to go to disk. But `read(2)` doesn't talk to the disk directly. Between the syscall and the hardware there's the block layer - the kernel subsystem that manages I/O requests.[^queuescheduler]


The purpose of a scheduler like `mq-deadline` is to reorder requests. It sorts them by logical block address, batches reads and writes separately, and makes sure writes don't get starved. With `none`, there's no reordering - requests go straight through. On NVMe there's no seek penalty, so reordering is pointless overhead.

When a page cache miss happens, the kernel creates a `bio` structure (block I/O request) and submits it via `submit_bio()`. What happens then depends on the block layer's multi-queue architecture (`blk-mq`). There are two levels of queues: software queues and hardware queues. The software queues are per-CPU - each CPU has its own entry point, so there's no single lock bottleneck. If there's an I/O scheduler, requests sit in the software queue for reordering and merging (adjacent block requests can be combined into one). If the scheduler is `none` and there's nothing to merge, requests try to go straight to the hardware dispatch queue.

The hardware queue is the last step before the IO request. But if the device can't accept more requests - because it's at capacity - the block layer puts the overflow in a dispatch list (`hctx->dispatch`) to be sent later. This is where requests pile up under saturation.

```
/*
 * Any items that need requeuing? Stuff them into hctx->dispatch,
 * that is where we will continue on next queue run.
 */
```

Our disk has a provisioned ceiling of 3000 IOPS. So what happens to request number 3001?

It waits. The hardware dispatch overflow grows. And as it grows, each request takes longer, because there are more requests ahead of yours. What was 1ms per read becomes 10ms. Then 50ms. The point is: the disk didn't get slower, but there are more requests in the queue.

## The death spiral

Say a query triggers a burst of page cache misses. A scan touching cold pages across a 49GB table, or vacuum walking 28GB of indexes. The kernel starts submitting hundreds of `bio` requests per second. The block layer queue grows. I/O latency spikes. Queries that finished in 50ms now take 5 seconds. That part is straightforward.

Lock amplification is the less obvious part. Postgres uses locks [everywhere](https://postgrespro.com/blog/pgsql/5967999). Row locks, relation locks, buffer mapping locks. Under normal conditions they're held for microseconds. But when a process acquires a lock and then hits a disk read that takes 200ms instead of 1ms, it holds that lock for 200ms longer. Another process needs the same lock, can't get it, and then waits. This second process shows up in `pg_stat_activity` with a `Lock` wait event, not an `IO` event. From the outside it looks like two separate problems. But the locking is a side effect of the I/O latency.

The other non-obvious part: the queue sustains itself after the trigger stops. Let's say vacuum was the trigger. Vacuum finishes. The trigger is gone. But by now you have 77 backend processes that accumulated during the storm. Each one has a query in progress. Each query still needs disk reads to complete. New queries keep arriving from the application. The arrival rate of I/O requests is still higher than what the disk can serve. The queue doesn't drain, and now the system is stuck: the only way to reduce I/O demand is to complete the queries, but completing the queries requires the I/O that's already saturated. 

Postgres has no mechanism to deal with any of this. It doesn't know about the IOPS ceiling. It doesn't know the block layer queue is deep. There's no backpressure, no admission control. Each new connection is accepted, a plan is made, execution starts, and the backend goes to sleep in the I/O queue like everyone else.

## A few words about vacuum

Autovacuum runs as a background process. Its job is to clean up dead tuples - the old row versions that updates and deletes leave behind. On our problem table there are 28GB of indexes. When vacuum runs, it doesn't just scan the heap for dead tuples. It has to walk every single index on the table to remove the pointers that reference those dead tuples. Every index page it reads is a potential `read(2)`. And on a table where the indexes don't fit in RAM, most of those reads miss the page cache and go to disk. A single vacuum run on this table can generate thousands of IOPS just from index maintenance.

Vacuum has a cost-based throttling system to deal with this. It does some work, counts the pages it touched, and sleeps for a configured delay (`autovacuum_vacuum_cost_delay`). The idea is that vacuum does a bit of I/O, pauses, lets real queries use the disk, does a bit more, pauses again.

But there's a problem: the throttling doesn't know anything about the actual I/O situation. Vacuum counts pages. It doesn't check the queue depth. It doesn't check the latency. If vacuum generates 500 IOPS and the disk has plenty of headroom, the throttling works fine - vacuum pauses, queries run, and everyone is happy. But if queries are already pushing 2500 IOPS and vacuum adds 500, you blow past the 3000 ceiling. Same vacuum configuration, same cost delay, but a completely different outcome depending on what else is happening on the disk.

And vacuum can be both the trigger and the victim. It starts a run, generates enough reads to saturate the disk, and then its own reads get stuck in the queue behind everything else. A vacuum run that finishes in 30 seconds under normal conditions can take 20 minutes under saturation. And the entire time it's generating more I/O and holding cleanup resources, feeding the same saturation that's slowing it down.

## The queries that lit the match

Both of our worst query patterns do the same thing: scan an index on `account_id`, fetch thousands of rows from the heap, apply JSONB filters after the fetch, and discard almost everything.

Let me show you what this looks like:

```
Index Scan using idx_account_id on core_lead
  Index Cond: (account_id = 4939)
  Rows Removed by Filter: 39811
  Buffers: shared hit=10871 read=27841
  I/O Timings: shared/local read=13838.335
```

Look at those numbers. 39,811 rows fetched from disk. All of them discarded by the filter. Zero rows returned. 27,841 block reads at 8KB each - that's 217MB read from disk. Over 14 seconds of execution, that's ~1,989 IOPS. From a single query. That returned nothing.

Why does this happen? The index only knows about `account_id`. It tells Postgres "account 4939 has 39,811 rows, and here's where they are on disk." But the JSONB conditions and the NULL checks in the WHERE clause - that information only exists in the heap, in the actual row data stored on disk. So Postgres has to follow the index to every single row location, read the page, check the filter, and throw the row away. It does this 39,811 times.

Two of these queries running at the same time generate almost 4,000 IOPS between them. On a 3,000 IOPS disk. That's already past the ceiling before vacuum, before checkpoints, before WAL writes, before anything else gets a turn.

This is how a query returning zero rows takes down a database.

## The wrong model

One thing that kept bugging me the whole time: load average. During incidents it was hitting 8 to 12 on a machine with 2 vCPUs. That's 4 to 6 times the number of cores. At first I thought: maybe the CPUs are the bottleneck, maybe processes are fighting for time on the cores.

But they weren't. Most of the backends were sitting in `IO:DataFileRead` - waiting on disk, not burning CPU. The bottleneck was the disk. That much was clear.

A quick note on `IO:DataFileRead`: this is a Postgres wait event, not an OS process state. Postgres has its own instrumentation that tracks what each backend is doing. When a backend shows `IO:DataFileRead`, it means Postgres called `read(2)` to fetch a data file page and is waiting for the call to return. It doesn't tell you what the kernel is doing with the process - the process could be in `D` state, `S` state, or something else. Postgres doesn't know. It just knows it called `read(2)` and hasn't gotten an answer yet.

What wasn't clear was the load average itself. I wrote about this a while back - Linux counts three things in load average: processes running on a CPU, processes in the run queue, and processes in uninterruptible sleep (`D` state). From the kernel source:

```
 * The global load average is an exponentially decaying average of nr_running +
 * nr_uninterruptible.
```

Processes in regular sleep (`S` state) don't count. So if load average was 12, those 12 processes were either running, runnable, or in `D` state.

During an incident, we killed backends that were in `IO:DataFileRead` using `pg_terminate_backend()`. And they died. `pg_terminate_backend` sends `SIGTERM`. If those processes were in `D` state, the signal would have been queued - they wouldn't have died immediately. I know this because I tested it[^dstate]. I once created a kernel module that forced a process into `D` state and tried to kill it:

```
root@debian:/proc/1506781# kill -9 1506781
root@debian:/proc/1506781# cat status | grep -i SigPnd
SigPnd: 0000000000000100
```

The signal sat there, pending. The process didn't die. That's the whole point of uninterruptible sleep.

But during the Postgres incident, the processes died. Which means they were probably in `S` state, interruptible. And if they were in `S` state, they wouldn't count toward load average. And load average was 12. So where was the load coming from?

Maybe some processes were in `D` and others in `S` - the ones we killed happened to be in `S` at that moment. Maybe they were transitioning between states and load average caught them in `D` at sampling time. Maybe the load was from the run queue - 77 processes context-switching on 2 cores generates its own pressure.

I don't have a clean answer. I know the processes died on `SIGTERM`. I know load average was 12. I don't fully understand what was happening between those two facts yet.

[^queuescheduler]: On my personal machine, for example, the I/O scheduler is set to `none`, with `mq-deadline` as the other option:

    ```
    root@debian:~# cat /sys/block/nvme0n1/queue/scheduler
    [none] mq-deadline
    ```
    Linux kernel docs has a great overview of IO schedulers: https://docs.kernel.org/block/blk-mq.html. I also found a nice article comparing different types of IO schedulers: https://www.admin-magazine.com/HPC/Articles/Linux-I-O-Schedulers. One thing to note, though, is how the docs mention the importance of hard drives for the Kernel. There are a lot of differences between hard drives and SSDs. One of the most interesting ones is the random read penalties in the two worlds. When I began to troubleshoot the IOPS problem, I had this in mind: what if we are doing random reads without noticing? Only after a few hours of study I understood: oh damn, random reads penalty is not the same in SSDs. [The fun is over.](https://www.youtube.com/watch?v=Ujq-5Smtf0c&list=LL&index=1)



[^dstate]:
    
    I tried to create a `write` C program to emulate D (uninterruptible) task, but I failed. So I appealed to kernel modules:

    ```
    #include <linux/module.h>
    #include <linux/sched.h>
    #include <linux/delay.h>

    static int __init dstate_init(void) {
        set_current_state(TASK_UNINTERRUPTIBLE);
        schedule_timeout(60 * HZ);
        return 0;
    }

    static void __exit dstate_exit(void) {}

    module_init(dstate_init);
    module_exit(dstate_exit);
    MODULE_LICENSE("GPL");
    ```

    And then used make + insmod:

    ```
    obj-m += dstate.o

    all:
        make -C /lib/modules/$(shell uname -r)/build M=$(PWD) modules
    ```

    Executed:

    ```
    make
    insmod dstate.ko &
    [1] 1506781
    ```

    I'm forcing this C program to be compiled as a kernel module. `insmod` loads the .ko file into the running Kernel. 

    Let's find a few things about this process:

    ```
    dstate_initroot@debian:/proc/1506781# cat sched
    insmod (1506781, #threads: 1)
    -------------------------------------------------------------------
    nr_switches                                  :                    1
    nr_voluntary_switches                        :                    1
    nr_involuntary_switches                      :                    0
    ```

    The scheduler gave in the CPU one time. No forced preemption.

    ```
    root@debian:/proc/1506781# cat schedstat
    4285857 0 1
    ```

    ~4ms of execution time. 0ns waiting in runqueue, 1 switch.

    ```

    root@debian:/proc/1506781# cat status
    Name:   insmod
    Umask:  0022
    State:  D (disk sleep)
    SigPnd: 0000000000000000
    ```

    SigPnd (signals pending) is represend in hexadecimal, it shows 0 pending signals. So I sent a sigkill:

    ```
    root@debian:/proc/1506781# kill -9 1506781
    root@debian:/proc/1506781# cat status | grep -i SigPnd
    SigPnd: 0000000000000100
    ```

    Still `D`. The signal is pending, but the task won't die until it wakes up. That's the whole point of uninterruptible sleep: the kernel is protecting an operation that cannot be safely aborted. Not even kill -9 can force it.

    *!!! traces of despair*
    ```
    root@debian:~# strace -c -p 1506781
    strace: Process 1506781 attached
    ^C^C
    ^C^C^C^C
    ^C
    ^C^C^C^C^C^C^C
    ```
