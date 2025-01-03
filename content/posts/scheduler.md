+++
date = 2024-08-08
title = "Scheduler: notes from Remzi's lectures"
description = "Deep dive into Linux scheduler"
tags = ["Linux", "Scheduler"]
+++ 

(This the study notes I took while watching Remzi's lectures on operating system scheduler).

One of the most interesting topics in Unix systems is the scheduler. The scheduler is a part of the CPU virtualization, and scheduler implementation solves the highly complex problem: what and how to run processes?

The OS must, somehow, track processes that are running. And handle their states. The OS have **mechanisms** for this, for example: when the OS boots, it loads `traps`, or exception and interrupts handling mechanisms. So when a process needs something from the kernel -- privileged space -- it needs to make a system call. The system call interacts with the Kernel and runs the procedure there. So there an inter-communication that happens all the time between privileged space and unprivileged space. The OS also handles processes states: a process may be running, or may be ready to run, or maybe be a zombie (funny name, who had the idea?).

In any case, one of the things the OS should worry about is how to track "slow processes" (with IO). The OS must have a process list to track then all, and to come up with decisions about what to do in certain cases. For examplea: prog "A" -> trap (sys call to open) -> OS issues IO to disk -> a slow thing happens... -- In this case, the OS should knwo that this is a slow operation, and, for example, have mechanisms to now run prog "B" while IO happens for prog "A".

### **Policies**

The OS strives to be efficient while running processes, so it has to come up with policies to do it well. This is a highly complicated topic and, in my opinion, one of the most interesting ones in the OS field.

So, what should the OS runs?

**Runtime to completion**: the OS could simple run each task/process until it completes. It would be insanely inefficient, though. Imagine we have process A, B and C, and the scheduler runs them in a FIFO (first in, first out) algorithm. A runs until completion; then B, then C. Suppose that each one of team takes 100ms to complete. All of them would be completed in 300ms. But what if A runs for 1 minute? Process B and C would be waiting until A completes. So there must be an alternative to this.

**Shortest job first**: Instead, it would be interesting if the OS knew, somehow, the runtime of each job, and had the opportunity to run the shortest job first (SJF). Until now, though, we are assuming that all jobs arrive at the same time. But what if only A is running, and suddenly, like a wild pikachu, B appears? Suppose that B has the shortest run time of the two. What should the OS do? 

**Round robin**: In this policy, the OS runs a little slice of A, and then slice of B, and C, and then A again... The time that the OS runs the slices are called "quantum" or "time slice". This can work with a timer interrupt period. Example: every 10ms a slice runs. But we have a trade off: if we have short time slices, we have better response times, but tigh context switch overhead. Longer time slices have worse response time, but more efficient (fewer context switches).

One policy that was implemented in some Unix systems, but not in Linux, is the *Multi-level feedback queue*. This policy implements many queues. A job is on one queue at any given time, and this may change as the process runs. And each queue has a priority.

MLFQ has a few rules:

1) if priority (A) > Priority (B): A runs (and B doesn't).
2) If priority (A) == Priority (B): round robin between them.
3) where to start: with the highest priority.
4) if processes uses time slice at given priority, then at the end of the time slice, move down one level in the queue.


Let's suppose a scenario where we have a job A with a long runtime and smaller jobs C1, C2, C3 with short runtimes. Three queues: Q0, Q1, Q2. Q0 has the highest priority.

> -> A begins at Q0. -> Runs a little bit -> Goes to Q1 -> runs a little bit -> Goes to Q2 -> C1 appears -> A stops -> C1 runs at Q0. C1 finishes. ->  A runs at Q2 -> C2 appers -> A stops...

This has a big problem. If an infinite number of short jobs that will only run at the highest priority queue (in this case, Q0), A will never be resumed. Starvation for A. So, how to to ensure long-running jobs make progress? How to avoid starvation? A simple solution would be: if a job uses up slice time, it moves down. Another one: if a process waits too long, it moves up in the priority queue.[^1]

### **Linux**

But what about *Linux*, how does it implement scheduling? The Linux Programming Interface[^2] answers this question succintly: the default model for scheduling processes if *round-robin time-sharing*. Each processes is permitted to use the CPU for a bried period of time (time slices). And "processes can't exercise direct control over when and for how long they will be able to use the CPU". But Linux has the `nice` value, that allows the user to influence in the kernel's scheduling priorities. The `nice` attribute acts like a "weightening factor that causes the kernel scheduler to favor processes with higher priorities". And the beauty of it is that the user can set `nice` values.

The manpage for `sched`, though, gives a slightly different answer (check for yourself: `man 7 sched` on a Linux machine) because it takes into consideration another version of the Kernel (if you are interested, you can find a brief history of Linux schedulers [here](https://developer.ibm.com/tutorials/l-completely-fair-scheduler/)): the default scheduler is the **Completely Fair Scheduler** (another great name. Completely fair.). 

Linux also has *Realtime Process Scheduling* policies, which I'm not going to write about in this text. The reason for this policy, though, is to enable maximum response time (imagine, for example, a program like goolge maps). 

In summary, Linux implements several scheduling policies, including FIFO, Round Robin , and the Completely Fair Scheduler (CFS), to manage process execution and CPU time allocation efficiently.

[^1]: You can find much more about this on the OSTEP book, if you are interested: https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-sched.pdf
[^2]: https://www.amazon.com/Linux-Programming-Interface-System-Handbook/dp/1593272200

