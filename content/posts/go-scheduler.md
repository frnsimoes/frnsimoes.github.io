+++ 
date = 2024-09-28
title = "Taking a look at Go's runtime/proc.go"
tags = ["debugging"]
+++

I find that it's really interesting that Go has its own scheduler implemented in the user space. Reading `runtime/proc.go`, I got the big picture idea of how it works: A `G` (Goroutine) is just a part of the bigger scheme. When a Go program starts to run, it knows how many threads the machine has. That's the `P`, which represent logical processors. A `P` is tied with a `M`, a `worker thread`, which represents the OS thread itself.

With this model, Go can implement its own scheduler mechanisms, like context switch, creating and managing processes (represend by a Goroutine). Imagine that, every time the OS wants to switch between processes or threads, the kernel needs to save the execution of the running process (and its context), and loads the context of the new one. This takes time. Also, the OS has its own ideas about the process state, and different operating systems (and kernels) has its own idea about the best way to handle time sharing between processes. Context switch [has a cost]. In addition to that, a OS process/thread has it's own vision on what the address space should look like. Go has another. 

So, if we can implement our own control over the size of the process and the context switch, why not? A context switch has a price, and it can be a big one, depending on the scheduler that is implemented. Also, the operating system scheduler has its own ideas about when to context switch, which Go coudn't control. And since the main process operation in a Go program is the abstraction of a OS process called Goroutine, that has its own rules to operate, why not?

**How does it work?**

I found Dmitry Vyukov [design docs] for Go 1.14 scheduler, which talks about the addition of `P` in Go's concurrency model. It's a highly technical doc. 

Let's first try to define and investigate each entity of the scheduler:
- `M` is the OS thread. `M` is managed by the OS. In Go's runtime, it's called `M` (machine).
- `G` is the goroutine. A goroutine has its own stack, instruction pointer, etc. 
- `P` is the context, the local processor, the resource. 

When a Goroutine (`G`) is created, it's placed a data structure called `local run queue`, which is attached to `P`. If this local queue is full, `P` can push `G` to yet another data structure called `global run queue`, so `M` can pick it later. 

In this way, `P` can implement its own way of sharing resources between processes (goroutines). Go uses `gopark` and `gounpark` functions[^1] to achieve this. Park/Unpark is a concurrency technique. According to Remzi:

> The real problem with some previous approaches (other than the ticket lock) is that they leave too much to chance. The scheduler determines which thread runs next; if the scheduler makes a bad choice, a thread that runs must either spin waiting for the lock (our first approach), or yield the CPU immediately (our second approach). Either way, there is potential for waste and no prevention of starvation. (...) These two rou- tines (park and unpark) can be used in tandem to build a lock that puts a caller to sleep if it tries to acquire a held lock and wakes it when the lock is free.

Roughly speaking, parkking/unparking a goroutine simple means puting it to sleep. In technical terms, the goroutine enters the `waiting` state, while `P` puts another goroutine in the `running` state. This all happens in the local run queue, where `P` schedules which goroutine is going to run depending on its own rules (and not the OS rules).

**What happens when there's a network call?**

Whenever a goroutine makes a network call, the scheduler detach `G` from `P` and `M`, and puts `G` in the network poller[^2]. The network poller makes use of the IO multiplexing mechanisms of the OS: it uses `epoll`, for example, in linux systems, to create file descriptors that deals with events. I [wrote a little bit about this], if you are interested. This is ah igly interesting topic that deserves it's own investigation.

**What happens when there's a IO call?**

Whenever a Goroutine enters an intense IO call, the `G` and the `M` are detached from the `P`, and runs separately in the OS realm. So `P` can call another `M` to run other goroutines.After the IO is completed, the `G` is unpark and the goroutine can resume its execution.

There are still really interesting discussions about this topic. And Go maintainers are not fully satisfied with the current concurrency model. This [Github issue] has really interesting commentaries on introducing Linux Completely Fair Scheduler into Go's scheduler.

**Stealing processes**

Vyukov's docs also talks about implementing a process stealing[^3] scheduler. What does it mean? Go had many options of implementing a threaded execution: 1. run multiple user space threads on one OS thread; 2. one user space thread runs on one OS thread; 3. run multiple user space threads on multiple OS threads.This M:N model is faster, but much more complex than the others. The stealing process model exists to satisfy this model. When a `P` finishes execution a `G`, it tries to pop another `G` from its local run queue. When there's not `G` for it to run, it steals a `G` from another `P`, randomly. [Rakyll] has an excellent article on this model that is worth reading. Also, if you are interested in concurrency theory, take a look at the [notes] I took while reading OSTEP chapters on this subject



[^1]: https://github.com/golang/go/blob/eb6f2c24cd17c0ca1df7e343f8d9187eef7d6e13/src/runtime/proc.go#L418

[^2]: https://github.com/golang/go/blob/eb6f2c24cd17c0ca1df7e343f8d9187eef7d6e13/src/runtime/proc.go#L3839

[^3]: https://github.com/golang/go/blob/eb6f2c24cd17c0ca1df7e343f8d9187eef7d6e13/src/runtime/traceruntime.go#L533

[design docs]: https://docs.google.com/document/d/1TTj4T2JO42uD5ID9e89oa0sLKhJYD0Y_kqxDv3I3XMw/edit

[has a cost]: https://web.eecs.umich.edu/~chshibo/files/microkiller_report.pdf

[wrote a little bit about this]: /posts/io-multiplexing

[Github issue]: https://github.com/golang/go/issues/51071

[Rakyll]: https://rakyll.org/scheduler/

[notes]: /locks

