+++
date = 2025-04-08
title = "Sigterm a D state process"
labels = ["post"]
subjects = ["cpu", "production"]
+++

A kernel mystery I hit today: load average at 12 on a 2 vCPU machine during a production incident.

Linux [load average](https://www.brendangregg.com/blog/2017-08-08/linux-load-averages.html) counts three things: processes running on a CPU, processes waiting in the run queue, and processes in uninterruptible sleep - D state. From the kernel source:

    The global load average is an exponentially decaying average of
    nr_running + nr_uninterruptible.

Regular sleep doesn't count, so if load average says 12, those 12 were either running, runnable, or in D. A system doing heavy disk I/O can show high load average with near-zero CPU utilization.

Fine. My processes were waiting on disk, disk waits put processes in D state, D state counts toward load average, and load average was 12. No surprises here.

Then I killed them. I sent SIGTERM and they died immediately.

That shouldn't have worked. If a process is in D state, signals should get queued - the process shouldn't respond until the kernel wakes it up. That's the point of uninterruptible sleep: the kernel is protecting an operation that can't be safely interrupted. 

I was confused, so I tested it. Wrote a kernel module that forces a process into D state. Kinda hacky, I know, but this is what happened:

    set_current_state(TASK_UNINTERRUPTIBLE);
    schedule_timeout(60 * HZ);

Loaded it, confirmed the process was in D, and sent SIGKILL.

    root@debian:/proc/1506781# kill -9 1506781
    root@debian:/proc/1506781# cat status | grep -i SigPnd
    SigPnd: 0000000000000100

Signal pending, which means the process is still alive and in D state. [Bit 8 is set](https://www.kernel.org/doc/html/v6.9/filesystems/proc.html#:~:text=For%20example%2C%20to%20get%20the%20status%20information,shared%20p%20=%20private%20(copy%20on%20write)), SIGKILL confirmed. It stayed there for 60 seconds until the timeout expired and the kernel woke it up. Only then did it process the signal and die.

Even strace couldn't attach (traces of despair):

    root@debian:~# strace -c -p 1506781
    strace: Process 1506781 attached
    ^C^C
    ^C^C^C^C


What? I started searching for explanations, and found a few:

Processes don't stay in one state. A process doing disk I/O goes D, then S, then D, then S again as individual reads complete and new ones start. But, since load average samples every 5 seconds, maybe ones I killed might have been in an S window when the signal arrived.

Or run queue pressure - 77 processes on 2 cores. Even if most are sleeping, the ones that wake up create queue depth, and some of those 12 could have been runnable processes waiting for a core.

Or TASK_KILLABLE. [Since 2.6.25](https://lwn.net/Articles/288056/) there's a third sleep state: TASK_UNINTERRUPTIBLE | TASK_WAKEKILL. It shows up as D in /proc and counts toward load average, but it dies on fatal signals. Some filesystem code paths use it. If the I/O waits were hitting TASK_KILLABLE paths, that would explain everything - processes appear in D, contribute to load average, but die on signal.

That last one is the most satisfying explanation, and it resolves the contradiction completely.

I haven't traced the kernel code path to confirm it. So I'm not going to say that's what happened.

**Update, April 2026**

I traced the kernel code path. The third hypothesis was correct.

The generic buffered read path in mm/filemap.c does not use TASK_UNINTERRUPTIBLE. It uses TASK_KILLABLE.

When a process does a buffered file read and the page isn't in the page cache, the kernel needs to read it from disk. While waiting, filemap_get_pages puts the process to sleep using one of two functions: wait_on_page_locked_killable or lock_folio_killable. Both use TASK_KILLABLE as the sleep state.

```
int __folio_lock_killable(struct folio *folio)
{
    return folio_wait_bit_common(folio, PG_locked, TASK_KILLABLE,
                    EXCLUSIVE);
}
```

The non-killable version is right above it:

```
void __folio_lock(struct folio *folio)
{
    folio_wait_bit_common(folio, PG_locked, TASK_UNINTERRUPTIBLE,
                EXCLUSIVE);
}
```

TASK_KILLABLE is defined in include/linux/sched.h as:

```
#define TASK_KILLABLE   (TASK_WAKEKILL | TASK_UNINTERRUPTIBLE)
```

Processes that have the TASK_WAKEKILL flag are D, they add to loadavg, and they take on fatal signals.

And SIGTERM is a [fatal signal](https://unix.stackexchange.com/questions/490805/what-is-a-fatal-signal) when the process has no handler for it. For the kernel, a fatal signal is any signal whose default action is "terminate" and that hasn't been caught or ignored. The fact SIGTERM killed the process makes a lot of sense now.

So the full story: process does a buffered read, page misses the cache, filemap_read calls lock_folio_killable, process sleeps in TASK_KILLABLE, shows as D, inflates load average. I send SIGTERM. No handler installed so it's fatal. TASK_WAKEKILL wakes the process. Process sees the pending signal and dies.

This is why my kernel module test behaved differently. The module used raw TASK_UNINTERRUPTIBLE with no TASK_WAKEKILL flag. Mystery solved.
