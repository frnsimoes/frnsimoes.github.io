+++
date = 2024-07-04
title = "Exploring concurrency concepts"
+++ 


Just a post rumbling about threads, processes and green threads. These are my initial[^1] impressions on the topic.

A process is an instance of a running program. If we have two processes, each has its own address space in memory, and these addresses are mapped by the OS to their own physical addresses independently. They can both be scheduled on the CPU.

The state of the thread is very similar to the state of the process, though. It has a program counter, its own set of registers for computation. Also, the context switching is the responsible part to switch between threads.

If we have a process with two threads (grossly, a thread is something that can be run), we have two runnable parts that can share certain memory areas but can be scheduled independently by the OS scheduler.

Something interesting that Oz points out is the Linux way of thinking about threads and processes. The Linux kernel simplifies processes and threads by creating a [task struct]. A task is something that has state, can be scheduled, and tasks can potentially share memory mappings.

https://github.com/torvalds/linux/blob/master/include/linux/sched.h

In this code, a task has a [pointer to `mm`][pointer], which is the memory mappings. It means that if we create a new thread with `pthread_create`, a new task will be created that shares the same memory maps as the parent task (thread).

[^1]: For those who are curious, I'm studying operating systems with basically these three sources:
    - Tanenbaum's [Modern Operating Systems]
    - Remzi & Andrea's  [OSTEP]
    - Berkeley's [CS162] 

    Tanenbaum has a solid and profound academic approach. I like reading him first, then jumping to CS162, if necessary, and finally to the fun OSTEP provides. I like OSTEP because it's fun, deep and practical oriented at the same time, but I don't prefer it as my initial source.

[pointer]: https://github.com/torvalds/linux/blob/master/include/linux/sched.h#L888
[task struct]: https://github.com/torvalds/linux/blob/master/include/linux/sched.h#L748
[Modern Operating Systems]: https://www.amazon.com/Modern-Operating-Systems-Andrew-Tanenbaum/dp/013359162X
[OSTEP]: https://pages.cs.wisc.edu/~remzi/OSTEP/
[CS162]: https://archive.org/details/ucberkeley_webcast_6ZDrb0KlYhI
