+++
date = 2026-01-19
title = "Making sense of CPU utilization"
tags = ["favorite"]
+++ 

{{< figure src="/static/loadavg/loadavg.png" alt="" caption="" >}}

A few days back I had the following situation at work: we run a bunch of websockets in containers. These containers store users' sessions. When something unexpected happens to the websocket, the program makes a select in a database, fetches a few info, and tries to connect again - reviving the websocket. The container runs two programs: a node program and an engine. The two of them connects through a unix socket. 

I got an alert that the CPU utilization was spiking. Users were being disconnect. Customer service was fighting the storm. We had a few spikes of load average. This made me think in a lot of things, but one of them was: ok, 80% CPU spike, load average reaching 255? TCP sockets went from 1280 to 913 and to 2678. What is loadavg measuring?

Does it mean that 255 processes were forked and tried to run at the same time? What did the scheduler do at this point? Did the kernel load everything into memory? What's the connection between the physical level, the scheduler decisions, and the userland metric tools?

## CPU utilization

In other words, what is CPU utilization, really? Processes have multiple possible states: sleeping, runnable, running. Which count as CPU load? Which of them actually switch transistors and force the CPU to act the physical level?

There are three layers embedded in this questions: at the physical level, we have transistors making noise, and the only thing that matters there are the running instructions. At the software level, we have the kernel scheduler making decisions - his own algorithm, his view of what should be run and what should be idle, limitations from blocking actions. At the userland, we have metric tools to understand what's happening.

Each of these layers represent a different question. But for the final user - you and me - the userland metrics is what matters, especially if we are facing problems that affect people.

## The scheduler

You can have a fine and detailed explanation of the scheduler in Robert Love's book. [^Remzi] also has a great explanation of schedulers. What I want is to understand how the CFS (The completely fair scheduler, Linux's current scheduler implementation) handle context switching between runnable tasks (remember: a task in linux is either a process or a thread). This is how the Kernel documentation describes how the scheduler decides between tasks:

```
In CFS the virtual runtime is expressed and tracked via the per-task p->se.vruntime (nanosec-unit) value.  This way, it's possible to accurately timestamp and measure the "expected CPU time" a task should have gotten.
```

Two important concepts here: `vruntime` and the struct `cfs_rq` (sched/sched.h). `vruntime` is a property that shows how much time that task has had of CPU time. `cfs_rq` is a struct that tracks runnable tasks.

So suppose you have two tasks right now: one doing heavy processor-bound computation, and the other one a simple TCP socket listening for something. The first one consumes a lot of CPU time. The other one can be sleeping for a long time, until something enters the network stack and poke it. The scheduler is "fair", meaning that, if there's room to run, the next runnable task is the one with less `vruntime` - the TCP socket will likely be chosen, because it's almost always in a blocking (interruptible sleeping) state. 

Tasks that are not in a runnable state are not computed in the `cfs_rq` struct. If it's sleeping (our TCP socket process waiting for something), the kernel pops it out of the `cfs_rq` and puts it in a wait queue. 

## The userland tools

We have a few tools in the userland, the most interesting one is the loadavg[^loadavg] in `/proc/loadavg`. It shows how's the pressure in the last 1-, 5- and 15 last minutes. loadavg considers running tasks + sleeping uninterruptible tasks when computing CPU load:

```
 * The global load average is an exponentially decaying average of nr_running +
 * nr_uninterruptible.
```

`nr_uninterruptible` accounts for uninterruptible sleeping tasks (I kind of got excited about this and played a little bit with uninterruptible tasks, see at the end of the article).

Another thing that caught my eye while reading sched/fair.c:

```
 * CPU utilization is the sum of running time of runnable tasks plus the
 * recent utilization of currently non-runnable tasks on that CPU.
 * It represents the amount of CPU capacity currently used by CFS tasks in
 * the range [0..max CPU capacity] with max CPU capacity being the CPU
 * capacity at f_max.
 *
 * The estimated CPU utilization is defined as the maximum between CPU
 * utilization and sum of the estimated utilization of the currently
 * runnable tasks on that CPU. It preserves a utilization "snapshot" of
 * previously-executed tasks, which helps better deduce how busy a CPU will
 * be when a long-sleeping task wakes up. The contribution to CPU utilization
 * of such a task would be significantly decayed at this point of time.
```

This explains why scheduler utilization can remain high even when few instructions are actually executing. The CPY may be mostly idle at the physical level, while the scheduler still carries memory of recent pressure. One interesting detail about this is the `util_avg` in the `sched_avg` instruct (util_avg = running% * SCHED_CAPACITY_SCALE).

Tools that measure CPU utilization as a whole must account for multiple realities at once: what's now, what was a few time back, and the actual forecast of what's going to run. It's much more complicated thing than the actual running tasks at physical level. It's actually a way to handle the scheduler's abstraction limitations.

The Kernel dev even jokes about it (kernel/sched/loadavg.c):

```
 * This file contains the magic bits required to compute the global loadavg
 * figure. Its a silly number but people think its important. We go through
 * great pains to make it work on big machines and tickless kernels.
```

## What is actually running

At this point, it should be clear that each layer has a different opinion of what is actually running. From physical cycles in a loop to accounting to past, present and future in the userland tools. At the heart of all of this, two questions are being asked:

1. which tasks are executing instructions right now?
2. how busy does the scheduler believe the CPU is?


The first question has a physical answer while the second does not. From the scheduler’s point of view, utilization is an estimate. It mixess what is happening now with what happened recently, and with what is likely to happen soon.

This is why scheduler utilization can remain high even when few instructions are actually executing. The CPU may be mostly idle at the physical level, while the scheduler still carries memory of recent pressure.

The CPU is almost simple: it executes one thing after the other. The scheduler is a complex software construct, it's an abstraction, and, like all abstractions, it creates new limitations.

### A detour into uninterruptible sleeping tasks

This is quite interesting. Uninterruptible tasks are tasks that called some syscall (I/O) which cannot be interrupted. The operation must be completed.

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

SigPnd (signals pending)[^pnd] is represend in hexadecimal, it shows 0 pending signals. So I sent a sigkill:

```
root@debian:/proc/1506781# kill -9 1506781
root@debian:/proc/1506781# cat status | grep -i SigPnd
SigPnd: 0000000000000100
```

Still `D`. The signal is pending, but the task won't die until it wakes up. That's the whole point of uninterruptible sleep: the kernel is protecting an operation that cannot be safely aborted. Not even kill -9 can force it.

### Bonus: traces of despair
```
root@debian:~# strace -c -p 1506781
strace: Process 1506781 attached
^C^C
^C^C^C^C
^C
^C^C^C^C^C^C^C
```


[^Remzi]: https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-sched.pdf
[^pnd]: https://man7.org/linux/man-pages/man5/proc_pid_status.5.html
[^loadavg]: If you are interested in loadavg, I loved reading this article by Brendan Gregg: https://www.brendangregg.com/blog/2017-08-08/linux-load-averages.html
