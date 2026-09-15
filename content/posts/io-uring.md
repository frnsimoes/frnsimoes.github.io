+++
date = 2026-08-31
title = "io_uring without readahead"
labels = ["draft"]
+++

Someone [opened a PR](https://github.com/tursodatabase/turso/pull/8389) to implement readahead in Turso. It was a throwaway implementation, but a good excuse to measure io_uring and understand more about it.

Turso has two backends. `syscall` uses pread(2). `io_uring` uses io_uring, and opens the database file with O_DIRECT with no option to use buffered I/O. O_DIRECT takes away kernel readahead, so getting it back means implementing it in the application.[^backends]

Without readahead, io_uring issues only one entry at a time. The problem is the lack of concurrency: each read waits for the previous one. The application knows that "hey, at this time, I need page 100", which means: Turso submits a read SQE for page 100, then waits for it. The scan continues. Now Turso needs page 101, so it submits a new read SQE that page.

With readahead on, things change. Turso needs page 100, detects sequential access, and instead of asking for one page it submits reads for pages 100 through 131. Now 32 reads are in flight at the same time.

The measurements below use [TPC-H](https://www.tpc.org/tpch/)[^TPC-H], a standard benchmark for analytic databases, on a 1.2 GiB database.

- Q6, the query I measured, does a full scan on `lineitem`, the biggest table of the benchmark.
- `off` means `PRAGMA prefetch_pages=0`: The PR's code without readahead.
- `on` means a window of 32 pages.

## Request merging

I wanted to see what readahead changes in the I/O path: how many requests Turso submits, and what arrives at the device. So I ran `iostat -dxm 1 sda` alongside Q6, and `perf stat` counting the `io_uring:io_uring_submit_req` tracepoint.

| | off (n=1) | on (n=1) |
|---|---:|---:|
| SQEs submitted | 195,207 | 218,212 |
| device requests | ~196,000 | ~16,300 |
| `rareq-sz` | 4.37 KiB | 56.53 KiB |
| `%rrqm` | ~0 | 91-93% |

`rareq-sz` is the average size of a read request arriving at the device. `%rrqm` is the percentage of read requests *merged* with another request before being issued. The "device" here is the guest's virtual disk: these numbers do not refer to the physical storage under the VM.

With readahead on, Turso emits 23,005 more SQEs, and it fetches more pages than needed, making the device read more bytes. But the device receives fewer requests.

If two requests in the queue cover sectors that are next to each other, the block layer joins them into one bigger request. This only works if both requests are in the queue at the same time. I counted the merge tracepoints with perf.

With readahead off, only 140 of 195,516 bios merged. It makes sense since there's only one SQE in the queue and there's nothing to merge. With readahead on, 202,539 of 218,493 bios merged, and the device received only 15,951 requests. Since there were multiple SQEs in the queue, the kernel merged them.

## The polling thread

Turso uses io_uring with sqpoll. The sqpoll uses a thread that spins checking if work was delivered and if the kernel should do something. It's a thread that keeps track of work, at the cost of spinning.

I timed the execution of sqpoll with prefetch_pages=32 to see where the time was being spent: 8.22s of wall time, 3.70s of user time and 8.46s of system time (median of seven runs). The system time is bigger than wall time, and this is only possible when two threads spend CPU at the same time.

I expected the cycles to be in the query code, but:

{{< flamegraph src="/iouring/q6-sqpoll-all.svg" caption="Q6 on the io_uring backend with SQ polling. `io_sq_thread`, the kernel polling thread, is at 65% of cycles. This profile comes from a rebuilt host." >}}

So I rebuilt Turso without SQ polling, replacing the `setup_sqpoll` builder with the plain `IoUring::new`, which is already Turso's fallback when sqpoll setup fails.

Plain/default ring: 8.62s of wall, 3.62s of user, and 1.27s of system time. Removing the polling thread made wall time a little worse and the system time much smaller. The system time isn't zero because we are still calling `io_uring_enter(2)` per submission, and Turso submits one SQE at a time.

If polling is worth it or not depends on the machine. Didona et al. measured this in a [2022 SYSTOR paper](https://atlarge-research.com/pdfs/2022-systor-apis.pdf): submission polling with one NVMe drive and one CPU core reached only 13 KIOPS (13 thousand IO operations per second) - the two threads had to share one core, so they took turns. With a second core, performance completely recovered. This box I'm using has 4 vCPUs. The query is single-threaded and uses one ring with one polling thread, so there were enough CPUs for the polling thread to run without competing with the query.

## Cache misses

With SQ polling off, I timed Q6 again on both backends: 8.55s on io_uring and 3.02s on syscall. The difference is significant. I want to understand where that extra time goes, so I counted instructions and cache misses with perf. One note about the counters in this table: they come from a rebuilt host (who wants to pay Hetzner for idle time?), so their absolute values don't match the timings above.

| backend | cycles (median, n=7) | instructions (median, n=7) | IPC | cache misses | miss rate |
|---|---:|---:|---:|---:|---:|
| io_uring plain | 5.374 B | 21.497 B | 3.999 | 10.666 M | 13.255% |
| syscall | 4.734 B | 21.297 B | 4.499 | 5.889 M | 7.691% |

io_uring runs 0.2 B more instructions which is almost nothing, but it takes 4.8 M more cache misses.

Both backends use DMA: the disk hardware writes the data into RAM by itself, without the CPU doing the work. But there are differences between the two backends as well: in a buffered read, the disk writes the data into the page cache.[^pagecache] Then the kernel copies the data from the page cache into the process buffer. A side effect of copy: the data ends up in the CPU caches (L1/L2/L3).

With O_DIRECT, though, the disk writes the data into the process buffer directly without the copy step, which means the CPU doesn't get involved in the process, so nothing reaches the CPU caches.

This explanation is a hypothesis, the counters show that io_uring has more cache misses than syscall, but I never traced the misses back to the missing copy step.

## Costs

After all of this, I have some opinions about the cost of each model:

- sqpoll is a reasonable model when the machine has more than one vCPU. But you still need to understand how your application uses resources. If the application is already CPU heavy, the polling thread will compete with it for CPU. In that case, it's a good idea to measure the impact of dedicating one vCPU to the kernel thread before turning sqpoll on.
- plain/default io_uring is also reasonable, because it can batch. Only one `io_uring_enter(2)` batches multiple SQEs. The SYSTOR paper measured this: 1.01 syscalls per I/O at queue depth 64.


[^pagecache]: This is an interesting blog post on userland [disk I/O](https://transactional.blog/how-to-learn/disk-io), if you are interested.

[^backends]: ScyllaDB blog has a great explanation of I/O internals: https://www.scylladb.com/2024/11/25/database-internals-working-with-io/

[^TPC-H]: I used TPC-H because it's the recommended approach in Turso's CONTRIBUTION.md: https://github.com/tursodatabase/turso/blob/main/CONTRIBUTING.md#tpc-h
