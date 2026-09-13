+++
date = 2026-09-08
title = "Swap, memory pressure and the Go GC"
labels = ["draft"]
# [build]
# list = "never"
+++

  <figure class="post-figure-margin">
    <img src="/gogc/prod-anon-rss-burst.png" alt="Grafana panel of anonymous RSS for the Go process in production: flat at 33 MiB, then rising to 570 MiB in about 15 seconds">
  </figure>


I recently ran into a problem with cgroup running two processes, with `memory.max` set to 900 MiB. The main process is a Go program with a baseline RSS of around 32 MiB; the other, a neighboring HTTP server, uses ~400 MiB. The problem was that, randomly through the day, the Go process would experience a massiv spike in anonymous memory, growing from 32 MiB to 500+ MiB, which triggered an OOM kill.

Since I don't actually have access to this code, and don't want to fork it to maintain our own version, I decided to run pyroscope.ebpf to check what was going on during heap spikes. And I found out that the Go process basically does the following during a spike: calls `io.ReadAll` then `proto.Unmarshal`. So we start with a blob of bytes and then deserialize it into a protobuf. We also spend a significant amount of time in `runtime.growslice`, which Go calls to grow the `io.ReadAll` slice when it reaches capacity.

  <figure class="post-figure-margin">
    <img src="/gogc/readall-flamegraph.png" alt="">
  </figure>

During the weekend I had an idea: ok, I don't want to fork this library, but what if I set `memory.high` and a swap to push the anonymous pages away from memory during spikes? Would that work? This sounded like a great idea. But I had a few questions:

- Swapping is a kernel's job. The kernel decides what to evict based on "accessed" and "active" flags it keeps in its internal LRU algorithm. Since I'm running two processes in the same cgroup, how do I know the kernel is going to evict the Go's heap and not the neighbor's process heap? 
- If this works and the kernel actually evicts the pages that were recently allocated, what will happen when the garbage collector runs and decides to read the heap and walk the `scan` spans?
- `memory.high` throttles the process/thread, but how would that look under load, if I would set it to, say, 700 MiB, a tight margin considering `memory.max` is 900 MiB?

Well, I had no alternatives but to measure. I built a mock program that allocates to the heap. The cgroup in this test is the same one I run in production: memory.max has 900 MiB. I set memory.high to 700 MiB.

First question: under continuous pressure, what really happens? Do we have something like a loop where keeps reading `scan` pages while the kernel keeps evicting them, leading to a spiral of major page faults and a back-and-forth between memory and swap? To answer this, I ran with a cgroup containing only one process, because I want to isolate the interaction between the GC and the kernel reclaim.

  <figure style="text-align: left">
    <img src="/gogc/churn-prod-full.svg" alt="">
  </figure>

Swap peaked at 500 MiB, so the back-and-forth is real. Since memory.high is set to 700 MiB, there's simply no room to keep the whole thing live in memory. The kernel evicts by age, and some of those pages are the ones the GC will read in its next cycle. So the GC faults them, and the kernel evicts other pages. This is also something Hertz et al noticed on the 2005 paper: "Because the mark-sweep based collectors do not perform compaction, objects become spread out over a range of pages. Once heap pages are evicted, visiting these pages during a collection triggers a cascade of page faults and orders-of-magnitude increases in execution time."

Also, take a look at the threads stalling I collected from [PSI](https://docs.kernel.org/accounting/psi.html) - memory pressure rise to 20-30% after swap fills. [`memory.high` throttles the allocating threads](https://elixir.bootlin.com/linux/v7.2.2/source/mm/memcontrol.c#L2505): The kernel makes them sleep to slow down allocation.

Second question: in the production setup, with the two processes sharing the same cgroup: what will the kernel do? Will it swap the Go's pages or the neighbor's? I ran the mock program with two different setups: in the first one, the neighbor's heap was allocated and not touched for the whole duration of the test. In the second, I forced a read from the heap every 15 seconds.

  <figure style="text-align: left">
    <img src="/gogc/spike-swap-compare.svg" alt="">
  </figure>


In the first setup, the neighbor's heap was never accessed after it was created, so the kernel evicted its pages first. In the second, the neighbor accesses its heap every 15 seconds. This makes the cycle repeat: the kernel evicts pages from both processes, and both processes later need to read some of those pages back from swap.

In 2005, Hertz et al wrote the [Garbage Collection Without Paging paper](https://people.cs.umass.edu/~emery/pubs/f034-hertz.pdf), which says that when an application does not fit memory, the GC can cause paging. My first test reproduced this: the process read 7.5 GiB from swap in four minutes, and threads were stalled for 9% of that time. The second test, with the idle neighbor, read only 4 MiB from swap in six minutes. And the third, with the neighbor actively reading its heap, read 2.1 GiB. So the worst case scenario is when the kernel has to swap-in a lot. This happens when there are no cold pages - which implies that there are not enough available memory for pages to age without being swapped.
