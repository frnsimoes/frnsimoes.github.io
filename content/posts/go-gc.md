+++
date = 2026-09-09
title = "A 40ms Go garbage collector pause"
labels = ["draft"]
[build]
list = "never"
+++

I recently had the chance to test the [5 minute rule to trade memory for disk access](https://dsf.berkeley.edu/cs286/papers/fiveminute-tr1986.pdf)[^1]. I'm running a cgroup with two processes. The main one is a Go program that spikes from 32 to 500+ MiB in RSS in only a few seconds, which triggers an OOM kill. The neighbor program is an HTTP server: baseline is around 400 MiB with no spikes. So I tried swapping. 

  <details>
  <summary>Setup</summary>

The setup in a few words: two processes in a 900 MiB cgroup with 500 MiB of swap on Hetzner box. The mock allocator: the neighbour holds 400 MiB and reads its own heap every 15 seconds. The Go process keeps 60 MiB live and, every 98 seconds, adds 300 MiB at 36 MiB/s, keeping it for 30 seconds. GOGC=100, GOMAXPROCS=2. Kernel 6.8. 17 spikes in 30 minutes. The mock allocator, ebpf scripts, and all there rest can be found in [this repository](https://github.com/frnsimoes/go-gc-swap-cost/blob/main/bpf/stw.bt) for reproduction

  </details>

Before running the experiment, my main concern was that the GC would ask the kernel to read pages that were on disk, which would [fault](https://www.linux.org.hk/archive/20260522-271-linux-kernel-developers-target-page-faul.html), and then the kernel would have to bring those pages back to RAM. That happend, but the cost of *reading metadata from swap* was the one that caught my attention the most. 

Here are the plots from metadata cost:

<img src="/gogc/hz-strip-metadata.svg" alt="">

The left plot shows we had 43 pauses that swapped-in. Maximum cost here was 40ms. The right plot is the size of the garbage collector's metadata during a spike - GC's metadata "other" doesn't shrink. I wrote a [small bpftrace script](https://github.com/frnsimoes/go-gc-swap-cost/blob/main/bpf/stw.bt) to understand what was happening, because either the garbage collector was hitting the disk while the world was stopped, or it was waiting for someone else who was hitting the disk.

The script is counting the page faults and recording where the process was when the faults occurred. Every long pause was essentially page faults. The script makes the fault probe only when `@stw_start[pid]` is set. 

The worst pause was `39902 us, faults during it 228, 39013 us in faults`: a 40ms pause with 228 page faults. 39ms of those 40 were spent in those faults. The script also saves the stack of the process at each fault, but bpftrace printed them as raw addresses because it couldn't read the binary's symbol. So I passed the addresses to `go tool addr2line` with the same binary (go 1.23) and it gave the function and source line for each trace:

```
0x42e5c8  runtime.(*spanSet).reset        mspanset.go:231
0x4219de  runtime.finishsweep_m           mcentral.go:71
0x4276a4  runtime.nextMarkBitArenaEpoch   mheap.go:2481
0x421a65  runtime.finishsweep_m           mgcsweep.go:268
0x4629cf  runtime.gcStart.func2           mgc.go:724
0x46dd8a  runtime.systemstack             asm_amd64.s
```

These are GC's [bookkeeping functions.](https://cs.opensource.google/go/go/+/release-branch.go1.23:src/runtime/HACKING.md;l=214). Go's runtime reuses those pages and doesn't free them. For example: [runtime.reset](https://cs.opensource.google/go/go/+/release-branch.go1.23:src/runtime/mspanset.go;l=230) "resets a spanset which is empty. It also clean up any left over blocks". Then we have the [finishsweep_m](https://cs.opensource.google/go/go/+/release-branch.go1.23:src/runtime/mgcsweep.go;l=229) which only runs when the world is stopped and "ensures that all spans are swept".

And nextMarkBitArenaEpoch comments:

```
// nextMarkBitArenaEpoch establishes a new epoch for the arenas
// holding the mark bits. The arenas are named relative to the
// current GC cycle which is demarcated by the call to finishweep_m.
```

That's a potential failure mode that I didn't know about. Go's GC has to stop-the-world in two moments: when it performs a [sweep termination](https://cs.opensource.google/go/go/+/release-branch.go1.27:src/runtime/mgc.go;l=24), and when it performs a [mark termination](https://cs.opensource.google/go/go/+/release-branch.go1.27:src/runtime/mgc.go;l=61), and at those moments it was trying to access those pages that had been swapped by the kernel. 

So here is what happens:

The runtime allocates those pages. They are not freed, but reused. Those pages are read in GC cycles, which don't happen that often. Because the kernel evicts pages [by age](https://elixir.bootlin.com/linux/v6.8/source/include/linux/mmzone.h), it sends the least accessed pages to swap. The GC runs, stops the world, tries to read those pages, but now we have a major page fault, the kernel needs to read PTEs, get the offsets of where those pages are on the swap disk, read those pages, find new frames for them in memory, wait for the disk, put them back in memory - just to keep it short.

Those 40ms seems inoffensive when read blunt. But we are talking about a stop-the-world pause. Those 40ms means everything stopped, including in-flight requests. 40ms is 800 times the median of the pause latency. It happens two or three times per memory spike. *It is* a lot. Swap has a bad reputation overall in the industry. For example: [Elasticsearch says swap is bad for performance](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/setup-configuration-memory), but [Chris Down](https://chrisdown.name/2018/01/02/in-defence-of-swap.html) is right. Swap *may be good depending on the nature of your problem*. In my case, it was good enough - even though I decided not to use it. But had I been running low-latency software, I would never use it. 

---
Notes: I mentioned other costs. The allocator cost is the most important one I found - mail me if you need more information.

The mock allocator allocates a batch of 560 KiB of objects. Without swap the allocation costs 3 to 5 ms. But when pages are in swap, during spikes, the same batch took 105 ms on the NVMe and 903ms on the network disk. Why does this happen? The runtime reuses memory that was freed earlier. If that memory is on disk, [the runtime has to zero it](https://cs.opensource.google/go/go/+/release-branch.go1.27:src/runtime/malloc.go;l=65) - which means bringing it back to RAM


[^1]: Also check: https://queue.acm.org/doi/10.1145/1413254.1413264


