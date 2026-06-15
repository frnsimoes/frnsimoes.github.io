+++
date = 2026-03-21
title = "Where did 400 MiB go?"
labels = ["post"]
subjects = ["memory", "production"]

+++

I restarted all 60+ pods of a Node.js websocket app earlier today. Every single pod sitting at ~330 MiB of memory. Except one, which was double the rest - at 640 MiB.

This is a statefulset. Memory jumped instead of growing gradually: ~230 MiB baseline, then a step to ~400 around 18:30, stabilized around 310, then another jump to ~640 at 20:00 and flatlined there. Discrete jumps, not a slow climb. Something was allocating memory in bursts and never releasing it.

This pattern wasn't new to me. Some pods would spike during fetch bursts and come back down. Others would spike and stay there permanently. 

I had a perfect isolation scenario: one sick pod, sixty healthy ones. All with the same image, configuration, and roughly same number of websockets. The only difference was that an automation tool had been hammering this specific pod with message fetch requests. I SSH'd into the node to check what was going on.

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

Gows is the websocket proxy (written in Go) - 89 MiB. And node dist/main - the actual Node.js application - at 680 MiB.

I ran the same commands on a healthy pod - dist/main at 268 MiB and gows at 82 MiB. The entire delta - all 412 MiB (!) - was in the Node.js process.

I pulled smaps_rollup from both processes. 

|  | sick | healthy |
|---|---|---|
| Pss_Anon | 615 MiB | 209 MiB |
| Pss_File | 11.7 MiB | 11.7 MiB |
| Shared_Clean | 65.5 MiB | 65.5 MiB |

All the growth was in private dirty anonymous memory. We had no file-backed growth and no shared memory changes. The shared libraries were identical - same binary and .so files loaded.

At this point I was fairly sure it was V8 heap. Made sense with the step-change pattern too - each burst of fetches creates a bunch of objects, V8 expands its old generation, and it never gives those pages back to the OS.

Well, I was wrong. Or at least, not entirely right.

I needed to see what V8 actually thought about its own memory. I used -USR1 and printed process.memoryUsage().

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

Ok, if it's not V8 heap, not external buffers, not array buffers, then where is it? The next obvious candidate are glibc's arenas. So I counted anonymous memory mappings in /proc/pid/smaps from both pods:

```
Sick:    1803 mappings
Healthy:  580 mappings
```

1803 vs 580. I shipped MALLOC_ARENA_MAX=2 to limit glibc to 2 arenas.

It didn't work. A pod got hammered, spiked to 576 MiB, and stayed there. I was missing something.

So I went back in. This time I checked the size distribution of those anonymous mappings on the stuck pod:

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

All 256 KB. 1461 separate memory regions, all exactly the same size.

This couldn't be glibc. With MALLOC_ARENA_MAX=2, there were only 2 arenas, and glibc grabs memory in much larger chunks anyway. So what allocates thousands of identically-sized 256 KB regions via mmap()? The only component in this process that manages its own memory like this, bypassing malloc() entirely, is V8. 1461 * 256 KB ~ 365 MiB of heap pages sitting in memory.

But process.memoryUsage() had reported heapTotal at only 129 MiB. How does V8 have 365 MiB of mmap'd pages but only report 129 MiB?

process.memoryUsage() reports heapUsed, which are the live objects V8 currently knows is in use. On the sick pod, 121 MiB. On the healthy one, 100 MiB. So I concluded V8 was fine and the problem was somewhere else.

I used the Chrome DevTools Protocol to force a full garbage collection on the stuck pod, then checked memory:

```
Before GC: RSS = 568 MiB, heapTotal = 129 MiB
After GC:  RSS = 316 MiB, heapTotal = 107 MiB
```

252 MiB gone.

So the V8 theory was right all along. But was glibc arena fragmentation also real, or had I been chasing the wrong thing entirely?

I properly tested both this time.

The first try was with --max-old-space-size=256 only. This caps V8's old generation heap at 256 MiB, forcing it to actually collect garbage instead of sitting on it forever. I hammered the pod. Memory spiked to 619 MiB during the burst, then dropped to 350 MiB. Better. But 350 is still above the ~250 MiB baseline.

Then I added MALLOC_ARENA_MAX=2 back. This time it dropped to 280 MiB.
