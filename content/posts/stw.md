+++
date = 2026-09-13
title = "A 40ms Go GC pause caused by swap"
labels = ["draft"]
image = "/gogc/hz-strip-pauses-og.png"
[build]
list = "never"
+++


I'm writing this so you don't slap your forehead like I *almost* did when I decided to run swap in production to absorb memory spikes.

I had a cgroup with two processes: one is a Go process that calls `io.ReadAll` and then `proto.Unmarshal`, creating a blob and then a graph struct (which is marked as `scan` by Go's allocator). The other process is an HTTP server that mostly stays quiet.

Whenever the collector runs, it reads those `scan` spans, pointer by pointer, and decides what to do with them. So I thought: ok, under memory pressure, the kernel is going to evict pages to the swap device, but since the eviction is per cgroup, and not per process, both processes' pages are going to be evicted - so there is only a small chance that this will turn into a sad dance of swap-in and swap-out between the kernel and the garbage collector.

I was wrong. While experimenting with this, I found a problem that could've hurt me: Go's garbage collector reads its metadata (outside the heap, in a region that is not [freed](https://cs.opensource.google/go/go/+/release-branch.go1.23:src/runtime/HACKING.md;l=214)) in a stop-the-world pause, and that metadata can be in swap.

I did a mock run on a Hetzner box using kernel 6.8 with MGLRU enabled[^1]. The median pause was around 51 us. With the metadata on the NVMe, the worst pause was 40ms.

{{< figure src="/gogc/hz-strip-pauses.svg" alt="alt" caption="">}}

To check where those 40ms went, I wrote a small [bpf script](https://github.com/frnsimoes/go-gc-swap-cost/blob/main/bpf/stw.bt) that counts page faults while the world is stopped. This was the worst one: `39902 us, faults during it 228, 39013 us in faults`. 39 of those 40ms were spent in 228 page faults. Those faults happened inside the GC's bookkeeping:

```
// addr2line output
0x42e5c8  runtime.(*spanSet).reset         /usr/local/go/src/internal/runtime/atomic/types.go:194
0x4219de  runtime.finishsweep_m            /usr/local/go/src/runtime/mcentral.go:71
0x4629cf  runtime.gcStart.func2            /usr/local/go/src/runtime/mgc.go:724
0x46dd8a  runtime.systemstack              /usr/local/go/src/runtime/asm_amd64.s:518
0x4169dc  runtime.gcStart                  /usr/local/go/src/runtime/mgc.go:722

0x4276a4  runtime.nextMarkBitArenaEpoch    /usr/local/go/src/runtime/mheap.go:2481
0x421a65  runtime.finishsweep_m            /usr/local/go/src/runtime/mgcsweep.go:268
0x4629cf  runtime.gcStart.func2            /usr/local/go/src/runtime/mgc.go:724
0x46dd8a  runtime.systemstack              /usr/local/go/src/runtime/asm_amd64.s:518
0x4169dc  runtime.gcStart                  /usr/local/go/src/runtime/mgc.go:722
```

That's a potential failure mode. Go's GC has to stop the world at two points: when it performs a [sweep termination](https://cs.opensource.google/go/go/+/release-branch.go1.23:src/runtime/mgc.go;l=24), and when it performs a [mark termination](https://cs.opensource.google/go/go/+/release-branch.go1.23:src/runtime/mgc.go;l=61). We had 312 of those pauses in 30 minutes. 

So here is why this happens: the runtime allocates those pages. They are not freed, but reused. Those pages are read in GC cycles. Because the kernel evicts pages [by age](https://elixir.bootlin.com/linux/v6.8/source/include/linux/mmzone.h), it sends the least recently accessed pages to swap. The GC runs, stops the world, tries to read those pages, but now we have a major page fault. The kernel needs to [read PTEs](https://elixir.bootlin.com/linux/v6.8/source/mm/memory.c#L5154), and then [call `do_swap_page`](https://elixir.bootlin.com/linux/v6.8/source/mm/memory.c#L5167), find a [new frame](https://elixir.bootlin.com/linux/v6.8/source/mm/swap_state.c#L454), [charge it to the cgroup](https://elixir.bootlin.com/linux/v6.8/source/mm/swap_state.c#L498), [read the pages](https://elixir.bootlin.com/linux/v6.8/source/mm/memory.c#L3913), [submit a bio](https://elixir.bootlin.com/linux/v6.8/source/mm/page_io.c#L482), [wait for the disk](https://elixir.bootlin.com/linux/v6.8/source/mm/memory.c#L3946), and put them [back in memory](https://elixir.bootlin.com/linux/v6.8/source/mm/memory.c#L4105) - just to keep it short.

Those 40ms seem harmless at first. But we are talking about a stop-the-world pause. Those 40ms mean everything has stopped - in Go's terminology, [every `P` has stopped](https://cs.opensource.google/go/go/+/release-branch.go1.23:src/runtime/proc.go;l=1586), so, for example, if a goroutine was waiting for I/O, during that pause the I/O might return and there would be no one to handle it. 40ms is 800 times the median pause. It happens two or three times per memory spike during the test. *It is* a lot. 

And then I noticed another thing: building one 511 KiB message, which usually takes 3-5 ms, jumped to 105 ms on the NVMe and 903 ms on Hetzner's network volume. Per message, this costs more than the metadata pause. But only the goroutine doing the allocation pays that price, so at least it's localized, and not global like the metadata one. 


{{< figure src="/gogc/hz-alloc-step.svg" alt="alt" caption="">}}

I haven't confirmed where that time goes, but even so I wanted to mention it here, because that's another cost you would have to pay. In any case, I agree with [Chris Down](https://chrisdown.name/2018/01/02/in-defence-of-swap.html), swap is not *evil*. But, yeah, it didn't behave well with garbage collection, and, in production, I'm collecting a lot.

---

**Update, September 14**. 

Someone asked me if Go 1.26’s [Green Tea garbage collector](https://go.dev/blog/greenteagc) changed the way the GC reads metadata. I measured it, and the impact is negligible.

  {{< figure src="/gogc/stw-fault-sites.svg" alt="alt" caption="">}}

[^1]: You can find everything about these experiments: plots, the mock allocator, bpf scripts, python scripts, etc., here: https://github.com/frnsimoes/go-gc-swap-cost



