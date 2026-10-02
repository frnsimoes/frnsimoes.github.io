+++
date = 2025-04-08
title = "Sigterm a D state process"
labels = ["post"]
+++

A kernel mystery I hit today: load average at 12 on a 2 vCPU machine during a production incident.

Linux [load average](https://www.brendangregg.com/blog/2017-08-08/linux-load-averages.html) counts three things: processes running on a CPU, processes waiting in the run queue, and processes in uninterruptible sleep - D state. From the kernel source:

    The global load average is an exponentially decaying average of
    nr_running + nr_uninterruptible.

Regular sleep doesn't count, so if load average says 12, those 12 were either running, runnable, or in D. A system doing heavy disk I/O can show high load average with near-zero CPU utilization.

Then I killed them. I sent SIGTERM and they died immediately. That shouldn't have worked. If a process is in D state, signals should get queued.

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

Processes don't stay in one state. A process doing disk I/O goes D, then S, then D, then S again as individual reads complete and new ones start. But since load average samples every 5 seconds, the ones I killed might have been in an S window when the signal arrived.

Or run queue pressure - 77 processes on 2 cores. Even if most are sleeping, the ones that wake up create queue depth, and some of those 12 could have been runnable processes waiting for a core.

I haven't traced the kernel code path to confirm it. So I'm not going to say that's what happened.
