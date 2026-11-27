+++
date = 2026-10-01
title = "Page table memory consumption"
labels = ["post"]
+++

The other day I was reading [Linus Torvalds punch some people](https://yarchive.net/comp/powerpc_page_tables.html) over hashed page tables. His argument: in a tree, the entries of neighboring pages are adjacent, which means one cache-line fills several TLB entries at once. A hash table, on the other hand, scatters neighbors in buckets:

> The fact is, you just don't know what GOOD actually is.

>I'll tell you: t a _good_ TLB fill should pre-populate the TLB with all
>the entries it can fit in one cache-line.  Do you realize that a
>bog-standard Intel CPU will fetch 8 TLB entries in one go? Together with
>a self-mapping (or, as Andy points out, you can just cache the other
>levels in dedicated caches), that means that with a single memory
>reference you get _eight_times_ the coverage that the silly Power hash
>tables get.



This discussion happened in 2003, in 1997, on his master's [thesis], he explains the adoption of the three multi-level page tables on the kernel. He seemed quite interested in latency, but maybe less interested in memory size:

> There are also secondary concerns: the virtual machine memory mappings must be memoryefficient, so that the mapping information does not take up a lot of physical memory that could be used to better advantage for file system caching or running user programs. 

In 2020, Shakeel Butt found the exact case where memory efficiency is not a secondary concern at all. [Shakeel](https://lore.kernel.org/linux-mm/20201126005603.1293012-1-shakeelb@google.com/#R) sent a patch adding a page table metric to `memory.stat`. [Roman Gushchin](https://lkml.rescloud.iu.edu/hypermail/linux/kernel/2011.3/06476.html) asked what was the use case for that statistic, arguing page tables are about 1/512 of mapped memory, which is under 1% of most cgroups ("for all but very large cgroups the value will be in the noise of per-cpu counters"). But Shakeel mentioned an [interesting case](https://lkml.iu.edu/hypermail/linux/kernel/2011.3/06492.html) he was seeing: a user space network driver that maps application memory for zero copy with a big `pgtables` usage.

Those 1/512 make sense when each page is mapped only once. But if N processes[^aspace] map the same page, each process needs its own PTEs for it. So the page tables cost about N/512 of memory they map. In general terms, this means that if you are running 512 processes with identical PTEs, the page tables cost as much as data pages.[^datapages]

Other issues similar to Shakeel's that I found while searching:

**Andrea Arcangeli, 2002.** [Andrea found](https://lkml.iu.edu/hypermail/linux/kernel/0201.2/0133.html) out why users with 64 GiB x86 machines were running out of memory even though there was a bunch of free memory in the system. Their workloads had hundreds of processes each mapping the same 1 GiB of shared memory. Data pages were shared, and each process needed its own page tables to map them - about 2 MiB with PAE[^PAE]. page tables live in the "lowmem" area, in 32-bit x86 that corresponds to ~896 MiB of physical memory. The patch moved the page tables from lowmem to highmem. This was an edge case scenario that only happened because users were using a 32-bit machine - with all the constraints of it, including lowmem - with a feature that allowed them to widen physical addresses. Pretty nice.

**Khalid Aziz, 2022.** 20 years later, [Khalid reported](https://lkml.rescloud.iu.edu/hypermail/linux/kernel/2201.2/03246.html) a similar problem: an Oracle database server with 512 GB of RAM crashing with OOM when 1500+ clients attached to a 300 GB SGA (shared memory). As in Andrea's case, data pages were shared, but each process needed its own page tables to map them. With 8-byte PTEs, 2 thousand processes mapping the same 4 KiB page need 16 KB of PTEs for that page. In the worst case, where every process maps the whole SGA, PTEs alone would take 878 GB. He proposed `mshare` to let processes share page tables. [As far as I checked](https://lore.kernel.org/all/?q=%22Add+support+for+shared+PTEs+across+processes%22), no version of mshare has been merged yet.

**Qi Zheng, 2021.** [Qi reported](https://lkml.rescloud.iu.edu/2109.0/01549.html) a process with 590 GiB RSS and 110 GiB of page tables (!), when mapping that much memory should only need around 1.2 GiB of PTEs. That workload used jemalloc and tcmalloc, which return memory to the kernel with `madvise(MADV_DONTNEED)` instead of `munmap()`[^munmap]. `MADV_DONTNEED` frees data pages and clears the PTEs, but keeps the page tables allocated, so empty page tables piled up[^sopel]. Unlike Andrea's and Khalid's cases, there were no shared mappings: it was a single process which kept page tables for freed memory. This patch got several rewrites, and was [merged in 2025](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=6375e95f381e3dc85065b6f74263a61522736203).

While these might read like edge cases from kernel mailing lists, the pattern is common: many processes mapping a large shared memory segment, each with its own page tables for it. I found two articles related to databases.

**Percona, 2021.** [Jobin Augustine reproduced](https://www.percona.com/blog/why-linux-hugepages-are-super-important-for-database-servers-a-case-with-postgresql/) a failure he kept seeing in production incidents: Postgres getting hit by OOM kills. 192 GB machine, shared buffers at 138 GiB, only 80 connections. page tables grew from 45 MiB to over 25 GiB as backends touched more of the cache. Memory got pressured and the machine started swapping. He solved the problem with huge pages: page tables stayed at 61 MiB for the same workload.

**ClickHouse, 2026.** [Kaushik Iska measured](https://clickhouse.com/blog/huge-pages-clickhouse-managed-postgres) the growth directly. A machine with 128 GiB and shared buffers at 32 GiB. Each backend scanning a 15.6 GiB cached table added 31 MiB of page tables. At 200 connections, page tables took 6.1 GiB. With huge pages, 200 connections only cost 111 MiB. 

Huge pages aren't free though. Reserving them needs unfragmented memory: ClickHouse notes that on a machine under load, "the same request routinely fails", and THP can stall on allocation. [In 2016, Mel Gorman](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=444eb2a449ef36fe115431ed7b71467c4563c7f1) proposed the kernel stop defragmenting for THP (Transparent huge pages) as default, "it's been years and it's time to throw in the towel". [Nelson Elhage](https://blog.nelhage.com/post/transparent-hugepages/) wrote about possible memory leaks and CPU usage issues that THP could cause. 

**The problem with page tables in NUMA machines**

New problems arrived with NUMA machines related to latency and memory size. With multiple nodes, a thread running on another node has to walk page tables in remote memory on TLB misses. [Mitosis](https://arxiv.org/pdf/1910.05398) (ASPLOS 2020) showed that remote page tables can slow down an application as much as remote data. And the [Hydra paper](https://www.usenix.org/system/files/atc24-gao-bin-scalable.pdf) (USENIX ATC 2024) reproduced this on a 8-socket machine with 8 TB of RAM. 

Mitosis's choice was to replicate the whole page table tree on every node - which costs memory (page table size * number of nodes), and every change has to update every copy. With Hydra, a PTE is only copied to a node when one of its threads faults on that node, and each page table page keeps a list of the nodes that hold a copy. 

In machines with multiple nodes, you either keep one copy of the page tables and pay the cost of reading remote tables on TLB misses, or you keep a copy on each node and pay to keep them in sync.

[^PAE]: x86-32 feature that widens physical addresses to 36 bits allowing 64 GiB of RAM.

[^munmap]: `munmap()` at some point calls [`free_pgtables`](https://elixir.bootlin.com/linux/v6.8/source/mm/memory.c#L362), which ends up calling [`free_pgd_range`](https://elixir.bootlin.com/linux/v6.8/source/mm/memory.c#L300).

[^aspace]: To be fair, N should be "address spaces", not "processes". Every task [`task_struct`](https://elixir.bootlin.com/linux/v6.18.6/source/include/linux/sched.h#L962) has a pointer to an `mm_struct`. 

[thesis]: https://www.cs.helsinki.fi/u/kutvonen/index_files/linus.pdf

[^datapages]: A data page has 4 KiB. Each PTE has 8 bytes. If 512 processes map the same page, they need 512 PTEs: 512 * 8 = 4 KiB.

[^sopel]: Sopel [pointed out on HN](https://news.ycombinator.com/item?id=49959214) that on Windows "zombie processes may use no memory but still keep >=32KiB page table". He encountered this himself with [an AMD iGPU driver bug](https://superuser.com/questions/1838566/how-to-identify-a-driver-causing-every-exited-process-to-become-a-zombie-pollut/1841517): "None of the processes that have ever been created finish." After 100,000 exited `cmd.exe` processes, RAMMap showed about 3.5 GiB of page tables.
