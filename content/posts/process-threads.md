+++
date = 2024-07-04
title = "First thoughts on processes, threads and green threads."
+++ 

A process is an instance of a running program. If we have two processes, each has its own address space in memory, and these addresses are mapped by the OS to their own physical addresses independently. They can both be scheduled on the CPU.

If we have a process with two threads (grossly, a thread is something that can be run), we have two runnable parts that can share certain memory areas but can be scheduled independently by the OS scheduler.

Something interesting that Oz points out is the Linux way of thinking about threads and processes. The Linux kernel simplifies processes and threads by creating a [task struct]. A task is something that has state, can be scheduled, and tasks can potentially share memory mappings.

https://github.com/torvalds/linux/blob/master/include/linux/sched.h

In this code, a task has a [pointer to mm], which is the memory mappings. One observation that might go beyond what I want to write:

- If I create a new thread with pthread_create, a new task is created that shares the same memory mappings as the parent task. This means the new thread operates within the same address space, allowing shared access to the same memory.
- If I create a child task with fork, though, I'm creating a new task that does not share the same memory mappings. Instead, it gets a copy of the parent task's memory mappings.

Back to it: Node.js and Python async do not make use of OS/Posix threads. These green threads work somewhat like this: there is a running process, say, the Node.js runtime, which is only one process (that's how the OS views the Node.js runtime process). The async functions are scheduled not by the OS scheduler, but by the event loop model.

Golang has an internal scheduler and can use OS threads. The Go runtime uses a combination of goroutines and a small number of OS threads to execute the goroutines. I'm still confused about this, though.

