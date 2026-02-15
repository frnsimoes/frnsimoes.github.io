+++
date = 2024-09-28
title = "Taking a look at runtime/proc.go"
description = "An overview of Golang's scheduler and concurrency"
+++

Concurrency and scheduling are hard topics. There are a few resources if you want to understand more about it. The OS implementation is a hard thing to understand, at least if you want to go deep into the details[^1]. Go's scheduler is an abstraction over the OS scheduler. So Go scheduler has its own rules, and, at the same time, makes use of POSIX threads. The scheduler can rapidly become a rabbit hole. So I thought about writing the few things I understood about it to at least paint a big picture of what's happening behind the scenes. 

What's the model of Go scheduler? `runtime/proc.go` presents three entities that, together, form the "process" model:

- `M` is the OS thread. `M` is managed by the OS and is called `M` (machine) in Go's runtime.
- `G` is the Goroutine. A Goroutine has its own stack, instruction pointer, etc.
- `P` is the context, the local processor, the resource.

In OS terms, `G` is the process/thread/task. `M` is the OS thread per se. And `P` is the logical processor, an entity the runtime create that matches every thread on the machine. In the runtime, `M` and `G` need to coexist dependently. 

This is the big picture: We have a `G` that is the thing that is going to run, the Go code. We also have the `P`, which is the context, the logical processor, which is attached to a `M`, the machine itself (the thread). A nice resource to understand more about this is [Morsing] blog post about the Go scheduler.

Now, how does the scheduler operate?

The scheduler makes use of two data structures: the local run queue, and the global run queue. The local run queue is attached to `P`. So, when runtime sees a `go` keyword to execute some routine, it places the `G` in the local run queue. If this data structure is full, `P` can push `G` to the global queue, so it can pick it up later. 

So far, so good. There is a data structure that stores processes and they are executed in order. 

What complicates things is the design introduced in Go 1.14. Check out Vyukov's [design docs] to get a glimpse of what it means. In Go 1.14, the scheduler started using the process stealing mechanism. Go had many options for implementing threaded execution: 1. run multiple user-space threads on one OS thread; 2. have one user-space thread run on one OS thread; or 3. run multiple user-space threads on multiple OS threads. This M:N model is faster but much more complex than the others. The stealing process model exists to satisfy this complexity. When a `P` finishes executing a `G`, it tries to pop another `G` from its local run queue. If there is no `G` for it to run, it randomly steals a `G` from another `P`. [Rakyll] has an excellent article on this model that is worth reading. Also, if you are interested in concurrency theory, take a look at the [notes] I took while reading OSTEP chapters on this subject.

So far we know the big picture model of the Go scheduler, and we also know a little bit about the basic data structures it uses to achieve time sharing between processes. 

But what happens when a `G` makes a network call, or enters an IO intensive task? Go uses the park/unpark concurrency model. The park/unpark[^2] is a lock model among others. And Remzi (the author of OSTEP) has a nice explanation on this model:

> The real problem with some previous approaches (other than the ticket lock) is that they leave too much to chance. The scheduler determines which thread runs next; if the scheduler makes a bad choice, a thread that runs must either spin waiting for the lock (our first approach) or yield the CPU immediately (our second approach). Either way, there is potential for waste and no prevention of starvation. (...) These two routines (park and unpark) can be used in tandem to build a lock that puts a caller to sleep if it tries to acquire a held lock and wakes it when the lock is free.

So when a `G` needs to do something that is not CPU intensive, the Go scheduler parks the `G`. This is also a tricky detail of implementation. Why? Go deals with parking in different ways, depending on what `G` is doing. If it's making a network call, the scheduler removes the `G` from `P` and parks it in the network poller[^3]. The network poller works more or less like Python or Javascript event loop on async calls: its implementation happens within the IO multiplexing universe. File descriptors are managed to read from events and write based on events. If you are curious about IO multiplexing, which is a really nice thing to understand, [I wrote a little bit about this].

### Why does Go need its own scheduler?

Now, if you are a systems nerd like me, you are probably asking yourself: why does Go need its own scheduler? The OS already has its own scheduler, made alive from the battle of many brilliant people. I searched, but I didn’t find a definitive or official answer by the maintainers. From the scheduler model, though, it's clear that Go is trying to hide the OS context switch cost. Go is also interested in creating its own abstraction of what a *process* is. A `G` starts with much less memory allocated than the POSIX thread. Also, the moment a context switch happens can have a significant impact on the efficiency of a process. Since we cannot control, in the user space, how the Kernel is going to context switch (different operating systems have different scheduler models; different kernels differ deeply, too), why not create an abstraction and get almost full control over the goroutine, to try to achieve rocket speed execution?

The scheduler model isn't perfect, though. There is a nice [GitHub issue] that talks about implementing Linux's most recent scheduler model into Go routines (the Completely Fair Scheduler). 

[^1]: I wrote a small text about the [OS scheduler](/posts/scheduler); and here are a few [notes](/locks) I took while reading OSTEP chapters on locks and threads, if you are interested.

[^2]: https://github.com/golang/go/blob/eb6f2c24cd17c0ca1df7e343f8d9187eef7d6e13/src/runtime/proc.go#L418

[^3]: https://github.com/golang/go/blob/eb6f2c24cd17c0ca1df7e343f8d9187eef7d6e13/src/runtime/proc.go#L3839

[design docs]: https://docs.google.com/document/d/1TTj4T2JO42uD5ID9e89oa0sLKhJYD0Y_kqxDv3I3XMw/edit

[context switch cost]: https://web.eecs.umich.edu/~chshibo/files/microkiller_report.pdf

[wrote a little bit about this]: /posts/io-multiplexing

[GitHub issue]: https://github.com/golang/go/issues/51071

[Rakyll]: https://rakyll.org/scheduler/

[notes]: /locks

[Morsing]: https://morsmachine.dk/go-scheduler
