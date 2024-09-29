+++
date = 2024-09-28
title = "Taking a look at Go's runtime/proc.go"
tags = ["debugging"]
+++

I find it really interesting that Go has its own scheduler implemented in user space. After reading parts of `runtime/proc.go`, I got the big picture of how it works: a `G` (Goroutine) is just one part of a larger scheme. When a Go program starts, the runtime knows how many threads the machine has. That’s the `P`, which represents logical processors. A `P` is tied to an `M`, a worker thread, which represents the OS thread itself.

With this model, Go can implement its own scheduling mechanisms, like context switching and managing processes (represented by `G`). Imagine that every time the OS wants to switch between processes or threads, the kernel needs to save the execution state of the running process (and its context) and load the context of the new one. This takes time. Moreover, the OS has its own ideas about process states, and different operating systems (and kernels) have their own methods for handling time-sharing between processes. Context switching [has a cost]. In addition, an OS process/thread has its own view of what the address space should look like, whereas Go has another.

So, if we can implement our own control over the size of the process and context switching, why not? A context switch has a price, which can be significant depending on the scheduler implemented. The operating system's scheduler has its own ideas about when to context switch, which Go cannot control. Since the primary operation in a Go program is the abstraction of an OS process called a Goroutine, which has its own rules to operate, it makes sense to take control.

**How does it work?**

I found Dmitry Vyukov's [design docs] for the Go 1.14 scheduler, which discusses the addition of `P` in Go's concurrency model. It’s a highly technical document.

Let's define and investigate each entity of the scheduler:
- `M` is the OS thread. `M` is managed by the OS and is called `M` (machine) in Go's runtime.
- `G` is the Goroutine. A Goroutine has its own stack, instruction pointer, etc.
- `P` is the context, the local processor, the resource.

When a Goroutine (`G`) is created, it’s placed in a data structure called the `local run queue`, which is attached to `P`. If this local queue is full, `P` can push `G` into another data structure called the `global run queue`, so `M` can pick it up later.

In this way, `P` can implement its own method of sharing resources among processes (`G`). Go uses the `gopark` and `gounpark` functions[^1] to achieve this. Park/Unpark is a concurrency technique. According to Remzi:

> The real problem with some previous approaches (other than the ticket lock) is that they leave too much to chance. The scheduler determines which thread runs next; if the scheduler makes a bad choice, a thread that runs must either spin waiting for the lock (our first approach) or yield the CPU immediately (our second approach). Either way, there is potential for waste and no prevention of starvation. (...) These two routines (park and unpark) can be used in tandem to build a lock that puts a caller to sleep if it tries to acquire a held lock and wakes it when the lock is free.

Roughly speaking, parking/unparking a Goroutine simply means putting it to sleep. In technical terms, the Goroutine enters the `waiting` state, while `P` puts another `G` in the `running` state. This all happens in the local run queue, where `P` schedules which Goroutine will run based on its own rules (not the OS rules).

**What happens when there's a network call?**

Whenever a `G` makes a network call, the scheduler detaches `G` from `P` and `M`, placing `G` in the network poller[^2]. The network poller makes use of the I/O multiplexing mechanisms of the OS: it uses `epoll`, for example, in Linux systems, to create file descriptors that deal with events. I [wrote a little bit about this] if you are interested. This is a highly interesting topic that deserves its own investigation.

**What happens when there's an I/O call?**

When a Goroutine enters an intense I/O call, both `G` and `M` are detached from `P` and run separately in the OS realm. This allows `P` to call another `M` to run other Goroutines. After the I/O operation is completed, `G` is unparked, and the Goroutine can resume its execution.

**Stealing processes**

Vyukov's docs also discuss implementing a process stealing[^3] scheduler. What does it mean? Go had many options for implementing threaded execution: 1. run multiple user-space threads on one OS thread; 2. have one user-space thread run on one OS thread; or 3. run multiple user-space threads on multiple OS threads. This M:N model is faster but much more complex than the others. The stealing process model exists to satisfy this complexity. When a `P` finishes executing a `G`, it tries to pop another `G` from its local run queue. If there is no `G` for it to run, it randomly steals a `G` from another `P`. [Rakyll] has an excellent article on this model that is worth reading. Also, if you are interested in concurrency theory, take a look at the [notes] I took while reading OSTEP chapters on this subject.

There are still fascinating discussions about the Go scheduler, and Go maintainers are not fully satisfied with the current concurrency model. This [GitHub issue] has really interesting commentary on introducing the Linux Completely Fair Scheduler into Go's scheduler.

[^1]: https://github.com/golang/go/blob/eb6f2c24cd17c0ca1df7e343f8d9187eef7d6e13/src/runtime/proc.go#L418

[^2]: https://github.com/golang/go/blob/eb6f2c24cd17c0ca1df7e343f8d9187eef7d6e13/src/runtime/proc.go#L3839

[^3]: https://github.com/golang/go/blob/eb6f2c24cd17c0ca1df7e343f8d9187eef7d6e13/src/runtime/traceruntime.go#L533

[design docs]: https://docs.google.com/document/d/1TTj4T2JO42uD5ID9e89oa0sLKhJYD0Y_kqxDv3I3XMw/edit

[has a cost]: https://web.eecs.umich.edu/~chshibo/files/microkiller_report.pdf

[wrote a little bit about this]: /posts/io-multiplexing

[GitHub issue]: https://github.com/golang/go/issues/51071

[Rakyll]: https://rakyll.org/scheduler/

[notes]: /locks
