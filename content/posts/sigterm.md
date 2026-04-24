+++
date = 2025-06-08
title = "Sigterm a D state process"
labels = ["favorite"]
subjects = ["cpu", "production"]
+++

Load average hit 12 on a 2 vCPU machine during a production incident.

Linux load average counts three things: processes running on a CPU, processes waiting in the run queue, and processes in uninterruptible sleep - D state. From the kernel source:

    The global load average is an exponentially decaying average of
    nr_running + nr_uninterruptible.

Regular sleep doesn't count, so if load average says 12, those 12 were either running, runnable, or in D. A system doing heavy disk I/O can show high load average with near-zero CPU utilization.

Fine. My processes were waiting on disk, disk waits put processes in D state, D state counts toward load average, and load average was 12. Makes sense.

Then I killed them. I sent SIGTERM and they died immediately.

That shouldn't have worked. If a process is in D state, signals should get queued - the process shouldn't respond until the kernel wakes it up. That's the whole point of uninterruptible sleep: the kernel is protecting an operation that can't be safely interrupted. Not even SIGKILL works.

I tested it. Wrote a kernel module that forces a process into D state:

    set_current_state(TASK_UNINTERRUPTIBLE);
    schedule_timeout(60 * HZ);

Loaded it, confirmed the process was in D, and sent SIGKILL.

    root@debian:/proc/1506781# kill -9 1506781
    root@debian:/proc/1506781# cat status | grep -i SigPnd
    SigPnd: 0000000000000100

Signal pending, the process still alive and in D state. [Bit 8 is set](https://www.kernel.org/doc/html/v6.9/filesystems/proc.html#:~:text=For%20example%2C%20to%20get%20the%20status%20information,shared%20p%20=%20private%20(copy%20on%20write)), SIGKILL confirmed. It sat there, unkillable, for 60 seconds until the timeout expired and the kernel woke it up. Only then did it process the signal and die.

Even strace couldn't attach, nothing gets through (traces of despair):

    root@debian:~# strace -c -p 1506781
    strace: Process 1506781 attached
    ^C^C
    ^C^C^C^C

So here's the contradiction. Load average was 12, processes were waiting on disk, I killed them with SIGTERM and they died instantly. But processes in D state don't die on signals. If they died on SIGTERM, they were probably in S state - but S state doesn't count toward load average.

A few possible explanations.

Processes don't stay in one state. A process doing disk I/O goes D → S → D → S as individual reads complete and new ones start. Load average samples every 5 seconds, so it could catch them in D at sampling time even if they spend most of their time in S. The ones I killed might have been in an S window when the signal arrived.

Or run queue pressure - 77 processes on 2 cores. Even if most are sleeping, the ones that wake up create queue depth, and some of those 12 could have been runnable processes waiting for a core.

Or TASK_KILLABLE. [Since 2.6.25](https://lwn.net/Articles/288056/) there's a third sleep state: TASK_UNINTERRUPTIBLE | TASK_WAKEKILL. It shows up as D in /proc and counts toward load average, but it dies on fatal signals. Some filesystem code paths use it. If the I/O waits were hitting TASK_KILLABLE paths, that would explain everything - processes appear in D, contribute to load average, but die on signal.

That last one is the most satisfying answer, and it resolves the contradiction completely.

I haven't traced the kernel code path to confirm it. So I'm not going to say that's what happened.

**Update, April 2026**

I traced the kernel code path. The third hypothesis was correct.

The generic buffered read path in mm/filemap.c does not use TASK_UNINTERRUPTIBLE. It uses TASK_KILLABLE.

When a process does a buffered file read and the page isn't in the page cache, the kernel needs to read it from disk. While waiting, filemap_get_pages puts the process to sleep using one of two functions: wait_on_page_locked_killable or lock_folio_killable. Both use TASK_KILLABLE as the sleep state. From current mainline:

```
int __folio_lock_killable(struct folio *folio)
{
    return folio_wait_bit_common(folio, PG_locked, TASK_KILLABLE,
                    EXCLUSIVE);
}
```

The non-killable version sits right above it:

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

processes with the TASK_WAKEKILL flag are shown as D, increment nr_uninterruptible, and count towards loadavg, but wake on fatal signals.

And SIGTERM is a [fatal signal](https://unix.stackexchange.com/questions/490805/what-is-a-fatal-signal) when the process has no handler for it. For the kernel, a fatal signal is any signal whose default action is "terminate" and that hasn't been caught or ignored. SIGTERM qualifies.

So the full path: process does a buffered read, page misses the cache, filemap_read calls lock_folio_killable, process sleeps in TASK_KILLABLE, shows as D, inflates load average. I send SIGTERM. No handler installed, so it's fatal. TASK_WAKEKILL wakes the process. Process sees the pending signal and dies.

This is why my kernel module test behaved differently. The module used raw TASK_UNINTERRUPTIBLE with no TASK_WAKEKILL flag. That's a genuinely unkillable sleep. Real filesystem I/O paths don't do that.

Conclusion: the contradiction was never a contradiction. Load average was 12 because TASK_KILLABLE processes count toward nr_uninterruptible. The processes died on SIGTERM because TASK_KILLABLE processes wake on fatal signals. Both things are true at the same time. Mystery solved.
