+++
date = 2026-03-21
title = "Where did 400 MiB go?"
labels = ["favorite"]
subjects = ["memory", "production"]

+++

I restarted all 60+ pods of a Node.js websocket app earlier today. Every single pod sitting at ~330 MiB of memory. Except one, which was double the rest - at 640 MiB.


![alt](/static/pmem/spike.png)

This is a statefulset. When I built the cluster, I estimated each pod's footprint: ~198 MiB base, plus ~25 MiB per websocket. With 30 websockets per pod, that's roughly 900 MiB. I was wrong about the per-websocket cost - it's lower than 25 MiB in practice. But I still had to set memory requests to nearly 1.5 GiB per pod to match the limit and avoid OOMKills because I knew our automation tool would hammer the pods and consume more than 1GiB of RAM[^aloc]. On 8 GB nodes with 5 pods each, that's almost the entire node consumed.

The Grafana panel told an interesting story: the memory didn't grow gradually. It jumped: ~230 MiB baseline, then a step to ~400 around 18:30, stabilized around 310, then another jump to ~640 at 20:00 and flatlined there. Discrete jumps, not a slow climb. Something was allocating memory in bursts and never releasing it.

I had been watching this pattern for weeks. Some pods would spike during fetch bursts and come back down. Others would spike and stay there permanently. 

I had a perfect isolation scenario: one sick pod, sixty healthy ones. All with the same image, configuration, and roughly same number of websockets. The only difference was that an automation tool had been hammering this specific pod with message fetch requests. I SSH'd into the node to check what was going on.

## Finding the right process

First question: which process inside the container is actually eating memory? Three processes were running on this container:

```
--- PID 2043462 ---
/usr/bin/tini -- /entrypoint.sh
VmRSS:      1152 kB
--- PID 2043476 ---
node dist/main
VmRSS:    679936 kB
--- PID 2043573 ---
/app/gows --socket /tmp/gows.sock
VmRSS:     90884 kB
```

tini is PID 1 - a tiny init that just forwards signals. 1 MiB. gows is the websocket proxy, sitting at 89 MiB. And node dist/main - the actual Node.js application - at 680 MiB.

I ran the same commands on a healthy pod. Node at 268 MiB, gows at 82 MiB. The gows difference was negligible. The entire delta - all 412 MiB (!!) of it - was in the Node.js process.

## Where inside Node.js?

I pulled smaps_rollup from both processes. This is a per-process file in /proc that breaks down memory by type - private vs shared, clean vs dirty, anonymous vs file-backed[^filemem].

|  | sick | healthy |
|---|---|---|
| Pss_Anon | 615 MiB | 209 MiB |
| Pss_File | 11.7 MiB | 11.7 MiB |
| Shared_Clean | 65.5 MiB | 65.5 MiB |

All the growth was in private dirty anonymous memory. We had no file-backed growth and no shared memory changes. The shared libraries were identical - same binary and .so files loaded.

Private dirty anonymous memory is the most "real" measure of what a process is using. It means: the process allocated this via malloc() or mmap(), wrote to it, and it belongs exclusively to this process. The kernel can't drop, share, or reclaim it without killing the process. And there were 406 extra MiB of it on the sick pod.

At this point I was fairly sure it was V8 heap. JavaScript objects piling up from all those message fetches, never getting garbage collected. Made sense with the step-change pattern too - each burst of fetches creates a bunch of objects, V8 expands its old generation[^v8gen], and it never gives those pages back to the OS.

Well, I was wrong. Or at least, not entirely right.

## Looking inside the running process

I needed to see what V8 actually thought about its own memory. Node.js has a useful trick for this: if you send SIGUSR1 to the process, it activates the V8 Inspector[^sigusr].

```
kill -USR1 2043476
```

The inspector opened on port 9229 inside the container's network namespace. I couldn't reach it from the host directly - the container has its own network namespace. But with nsenter -t <pid> -n, I could enter that namespace and connect. Claude helped me write a one-liner that opened a websocket to the inspector, sent a Runtime.evaluate command with process.memoryUsage(), and printed the result. This is essentially running JavaScript inside the live process without restarting it.

The sick pod:

```
{
  "rss": 697303040,
  "heapTotal": 135147520,
  "heapUsed": 126842024,
  "external": 25004037,
  "arrayBuffers": 33762595
}
```

The healthy pod:

```
{
  "rss": 281395200,
  "heapTotal": 113913856,
  "heapUsed": 104892656,
  "external": 23737321,
  "arrayBuffers": 32256735
}
```

|  | sick | healthy | delta |
|---|---|---|---|
| RSS | 665 MiB | 268 MiB | +397 MiB |
| heapTotal | 129 MiB | 109 MiB | +20 MiB |
| heapUsed | 121 MiB | 100 MiB | +21 MiB |
| external | 24 MiB | 23 MiB | +1 MiB |

V8 heap difference: 20 MiB. RSS difference: 397 MiB. The V8 heap was fine. JavaScript had no idea there was a problem. But the kernel saw 665 MiB of resident memory, and V8 could only account for ~180 MiB of it (heap + external + array buffers). **377 MiB existed outside of V8 entirely**.

## The native layer

If it's not V8 heap, not external buffers, not array buffers, then where is it?

When Node.js makes an HTTPS request, the actual work doesn't happen in JavaScript. OpenSSL handles the TLS encryption, zlib decompresses the response if it's gzipped, llhttp parses the HTTP headers - and they are all in C. Each of these allocates memory through malloc(), which goes to glibc. 

So the flow for a single fetch is something like: TCP bytes arrive → OpenSSL (decrypt) → llhttp (parse) → zlib (decompress) → V8 heap (JavaScript objects). Each step is a different C library calling malloc(). Only the last step lands on V8's managed heap. Everything before it is native memory that JavaScript can't see.

But I still didn't understand why this memory wasn't being freed. In theory, the fetches complete, then the response is parsed, then the data moves to JavaScript. The native buffers should be freed. And they probably *were* freed - from the application's perspective. The question was whether glibc was actually returning that memory to the OS.

I counted anonymous memory mappings in /proc/pid/smaps from both pods:

```
Sick:    1803 mappings
Healthy:  580 mappings
```

1803 vs 580. That looked like glibc [arena](https://sourceware.org/glibc/wiki/MallocInternals#Arenas_and_Heaps) fragmentation[^arenas]. I shipped MALLOC_ARENA_MAX=2 to limit glibc to 2 arenas.

It didn't work. A pod got hammered, spiked to 576 MiB, and stayed there. I was missing something.

## The 256 KB clue

I went back in. This time I checked the size distribution of those anonymous mappings on the stuck pod:

```
<64KB:   13
64KB-1MB: 1461
>1MB:    25
```

Almost all in the 64KB-1MB range. I listed the actual regions:

```
256KB 1e20080000-1e200c0000 rw-p 00000000 00:00 0
256KB 2efb440000-2efb480000 rw-p 00000000 00:00 0
256KB 3c708c0000-3c70900000 rw-p 00000000 00:00 0
256KB 48d9340000-48d9380000 rw-p 00000000 00:00 0
256KB 5a3a3c0000-5a3a400000 rw-p 00000000 00:00 0
...
```

All 256 KB. Every single one. 1461 separate memory regions, all exactly the same size.

This couldn't be glibc. With MALLOC_ARENA_MAX=2, there were only 2 arenas, and glibc grabs memory in much larger chunks anyway. So what allocates thousands of identically-sized 256 KB regions via mmap()? The only component in this process that manages its own memory like this, bypassing malloc() entirely, is V8. 1461 × 256 KB ≈ 365 MiB of heap pages sitting in memory.

But process.memoryUsage() had reported heapTotal at only 129 MiB. How does V8 have 365 MiB of mmap'd pages but only report 129 MiB?

## What tricked me

process.memoryUsage() reports heapUsed: live objects, what V8 currently knows is in use. On the sick pod, 121 MiB. On the healthy one, 100 MiB. Almost the same. So I concluded V8 was fine and the problem was somewhere else.

But heapUsed doesn't tell you how much memory V8 has really grabbed from the OS. V8 requests pages during fetch bursts, fills them with objects, and those objects eventually become unreachable. Garbage. The pages stay mapped, the garbage is still there, sitting in real physical memory. V8 just hasn't collected it yet.

And why would it? V8's default heap limit is in the gigabytes, and it was using ~129 MiB. Plenty of room. No reason to waste CPU on garbage collection.

I used the Chrome DevTools Protocol to force a full garbage collection on the stuck pod, then checked memory:

```
Before GC: RSS = 568 MiB, heapTotal = 129 MiB
After GC:  RSS = 316 MiB, heapTotal = 107 MiB
```

252 MiB gone. V8 was holding 252 MiB of collectible garbage and just wasn't collecting it.

## Two problems

So the V8 theory was right all along. But was glibc arena fragmentation also real, or had I been chasing the wrong thing entirely?

I tested both, properly this time. Same pod, same load.

First: --max-old-space-size=256 only, no MALLOC_ARENA_MAX. This caps V8's old generation heap at 256 MiB, forcing it to actually collect garbage instead of sitting on it forever. I hammered the pod. Memory spiked to 619 MiB during the burst, then dropped to 350 MiB. Better. But 350 is still above the ~250 MiB baseline.

Second: added MALLOC_ARENA_MAX=2 back. This time it dropped to 280 MiB.

Both problems were real. V8 was the bigger one - about 270 MiB of garbage it wasn't collecting. And glibc arenas were contributing another ~70 MiB of native memory fragmentation from the OpenSSL, zlib, and llhttp allocations that happen below JavaScript.

## The fix

![alt](/static/pmem/gc.png)

```
env:
  - name: MALLOC_ARENA_MAX
    value: "2"
  - name: NODE_OPTIONS
    value: "--max-old-space-size=256"
```

--max-old-space-size=256 puts pressure on V8's garbage collector. Instead of waiting until it hits a multi-gigabyte limit, V8 starts collecting as it approaches 256 MiB. Dead objects from fetch bursts get collected, and V8 releases those pages back to the OS.

MALLOC_ARENA_MAX=2 limits glibc to 2 memory arenas. Native allocations from OpenSSL, zlib, and llhttp get concentrated in fewer pools, and glibc has a better chance of returning freed memory to the kernel[^arenas].

I wouldn't use these settings on every app. If your threads are CPU-bound and allocating constantly, --max-old-space-size=256 means frequent GC pauses, and MALLOC_ARENA_MAX=2 means lock contention on malloc(). But this app barely touches the CPU. Peak usage across all 60+ pods is 0.12 cores, with most sitting near zero. The threads spend their time waiting for API responses. GC pauses and malloc contention are both invisible here.

On 8 GB nodes with 5 pods each, every MiB of phantom memory is capacity I'm paying for but not using.

---

[^aloc]: /u/gordonmessmer suggested an excellent resource on memory allocation for those who are new to these concepts: https://samwho.dev/memory-allocation/

[^filemem]: smaps_rollup vs /proc/meminfo: they answer different questions at different scopes. meminfo is system-wide - total RAM, free, cached. smaps_rollup is per-process - exactly how much memory a specific process is using, broken down by type. Private vs shared: is this page exclusive to this process, or shared with others via copy-on-write? Clean vs dirty: does this page match what's on disk, or has it been modified in RAM? Anonymous vs file-backed: was this page allocated from scratch (heap, mmap), or is it backed by a file on disk (shared libraries, memory-mapped files)? File-backed clean pages are cheap - the kernel can drop them and reload from disk. Anonymous dirty pages are the most expensive: they can only go to swap or stay in RAM.

[^v8gen]: V8 divides its heap into generations. New objects go into the young generation, a small space that gets collected frequently. Objects that survive multiple collections get promoted to the old generation, which is larger and collected less often. --max-old-space-size caps the old generation. https://nodejs.org/en/learn/diagnostics/memory/understanding-and-tuning-memory

[^sigusr]: SIGUSR1 and SIGUSR2 are user-defined signals with no default kernel meaning - applications install their own handlers. Node.js uses SIGUSR1 to activate the V8 Inspector, which speaks the Chrome DevTools Protocol (CDP) over websocket. This is the same protocol Chrome uses when you open developer tools. I connected from the host by entering the container's network namespace with nsenter, opened a websocket to 127.0.0.1:9229, and sent a Runtime.evaluate command. The inspector evaluated the JavaScript expression inside the live running process and returned the result. No restart needed.

[^arenas]: glibc's allocator uses [arenas](https://sourceware.org/glibc/wiki/MallocInternals#Arenas_and_Heaps) - separate memory pools for different threads to reduce lock contention on malloc(). The default cap is 8 × the number of CPU cores. Each arena grabs memory from the OS in large chunks via mmap(). When the application calls free(), glibc doesn't necessarily return the memory to the OS. It keeps it mapped for reuse. If there's even one live allocation in a mapped region, the whole region stays pinned. With many arenas, freed memory gets scattered across all of them. With 2 arenas, allocations are concentrated, and glibc has a better chance of returning freed memory to the kernel. Also: illustrated representation of arenas malloc I found interesting: https://codeberg.org/gordonmessmer/dev-blog/src/branch/main/malloc-arenas-illustrated.md

