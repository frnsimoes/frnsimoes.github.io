+++
date = 2026-03-21
title = "Where did 400 MiB go?"
labels = ["post"]
subjects = ["memory", "production"]
+++

Doing some routine upgrades tonight. I restarted 60 pods of a Nodejs websocket application. Every pod came back at ~250 MiB of memory. One of them soon started to be hammerd by some automation tool we have, and memory spike from ~250 to 600+ MiB. And stayed there.

This pattern wasn't new. I've been seeing this for months. Well, today I decided to understand what's happening. My first bet is the usual culprit: V8's garbage collection. 

```
--- PID 2043462 ---
/usr/bin/tini -- /entrypoint.sh
VmRSS:      1152 kB
--- PID 2043476 ---
node dist/main
VmRSS:    679936 kB
--- PID 2043573 ---
/app/go --socket /tmp/go.sock
VmRSS:     90884 kB
```

- "Go" is the websocket proxy - 89 MiB. 
- And node dist/main - the actual Node.js application - at 680 MiB.

All the growth was in private anonymous memory (615 MiB vs 209 MiB). No file-backed growth and no shared memory changes (Shared_Clean was the same 65.5 MiB on both pods). At this point I was pretty sure it was V8 heap. It made sense with the step-change pattern - each burst of fetches creates a bunch of objects, V8 expands its old generation, and the pages don't return to the OS. 

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


V8 heap difference: 20 MiB. RSS difference: 397 MiB. The V8 heap was fine. At this point I thought javascript had no idea what was happening. But the kernel saw 665 MiB of resident memory, and V8 could only account for ~180 MiB of it (heap + external + array buffers). 377 MiB existed outside of V8.

Ok, if it's not V8 heap, not external buffers, not array buffers, then where is it? The next obvious candidate are glibc's arenas. So I counted anonymous memory mappings in /proc/pid/smaps from both pods:

```
Sick:    1803 mappings
Healthy:  580 mappings
```

1803 vs 580. I shipped MALLOC_ARENA_MAX=2 to limit glibc to 2 arenas. It didn't work. A pod got hammered, spiked to 576 MiB, and stayed there. I was missing something.

So I started again. This time I checked the size distribution of those anonymous mappings on the stuck pod:

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

All 256 KB. 1461 separate memory regions, all the same size. This couldn't be glibc. With MALLOC_ARENA_MAX=2, there were only 2 arenas, and glibc grabs memory in much larger chunks anyway. So what allocates thousands of identically-sized 256 KB regions via mmap()? The only component in this process that manages its own memory like this, bypassing malloc() entirely, is V8. 1461 * 256 KB ~ 365 MiB of heap pages sitting in memory.

But process.memoryUsage() had reported heapTotal at only 129 MiB, remember? How does V8 have 365 MiB of mmap'd pages but only report 129 MiB? Turns out process.memoryUsage() reports heapUsed, which are the live objects V8 currently knows is in use. On the sick pod, 121 MiB. On the healthy one, 100 MiB. So I concluded V8 was fine and the problem was somewhere else.

I used the Chrome DevTools Protocol to force a full garbage collection on the stuck pod, then checked memory again:

```
Before GC: RSS = 568 MiB, heapTotal = 129 MiB
After GC:  RSS = 316 MiB, heapTotal = 107 MiB
```

252 MiB gone. So the V8 theory was right. But was glibc arena fragmentation also real, or had I been hunting the wrong thing entirely? I properly tested both this time. The first try was with --max-old-space-size=256 only. This caps V8's old generation heap at 256 MiB, forcing it to actually collect garbage. Pod was hammered again, memory spiked to 619 MiB during the burst, then dropped to 350 MiB. Better. But 350 is still above the ~250 MiB baseline, so I set malloc arena to 2 again. This time it dropped to around the baseline and stayed there. This allowed me to essentialy increase pod density by 100%, which in turn halved our costs with Kubernetes.

