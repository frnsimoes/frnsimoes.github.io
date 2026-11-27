+++
date = 2026-11-22
title = "A short history of read streams in Postgres"
labels = ["post"]
+++

This post is a small collection of things I found out while reading about read combining in Postgres. I did some tests in production, and I was really surprised by how a page already in shared buffers could affect read combining. If that page is in the middle of a range, Postgres splits what could have been one big read into two smaller ones. This bothered me. So I decided to investigate and found an interesting sequence in the mailing list.

In 2007, Heikki Linnakangas [proposed](https://www.postgresql.org/message-id/46405393.507%40enterprisedb.com) a sequential scan roadmap for Postgres. One of the problems Heikki was trying to solve was how to optmize Postgres' shared buffers when a table was larger than shared buffers. He argued that there's no point in spoiling shared buffers because the performance gains are minimal when the table is much larger than the buffer (say, 5 or 10 times more). Such scans also evicted other tables' data from the buffer if there was no activity. So he proposed that, instead, big tables should reuse a small ring of buffers within shared buffers.

Luke Lonergan [replied](https://www.postgresql.org/message-id/C3E62232E3BCF24CBA20D72BFDCB6BF803EB6A3F%40MI8NYCMAIL08.Mi8.com) with an idea that went beyond the buffer ring: readahead inside the heap scan itself. The kernel already did readahead, but Postgres still asked for one 8 KiB page per syscall. Luke wanted Postgres to read N buffers ahead, issuing contiguous reads to the OS, which would be much larger than a single page. But Heikki was [skeptical](https://www.postgresql.org/message-id/464073B7.4070304%40enterprisedb.com), since the OS should handle readahead anyway. At this point, Andreas Zeugswetter [pointed out](https://www.postgresql.org/message-id/E1539E0ED7043848906A8FF995BDA57901FD9726%40m0143.s-mxs.net) that doing it properly would need scatter-gather I/O, a single call that fills several buffers, and Gregory Stark [went further](https://www.postgresql.org/message-id/87bqgvz44y.fsf%40oxford.xeocode.com) by saying that the real win would require async I/O. 

Heikki's idea was [merged](https://www.postgresql.org/docs/release/8.3.0/) in Postgres 8.3.0. In 2009, the same [Greg Stark](https://www.postgresql.org/message-id/87ljw5c0lx.fsf%40oxford.xeocode.com) introduced prefetch with `posix_fadvise` for bitmap heap scans in Postgres 8.4. It also introduced `effective_io_concurrency` to control how aggressively Postgres prefetched pages through the OS.

In 2023, [Thomas Munro opened a thread](https://www.postgresql.org/message-id/CA+hUKGJkOiOCa+mag4BF+zHo7qo=o9CFheB8=g6uT5TUm2gkvA@mail.gmail.com) that became read streams in Postgres 17. 

> Hi,

> Currently PostgreSQL reads (and writes) data files 8KB at a time.

Postgres had a `preadv` wrapper since version 14. This proposal used it for data files, to merge adjacent blocks into one IO. The idea was somewhat close to what Luke and Andreas were discussing in 2007: ask for several pages at once, even though their locations in shared buffers aren't necessarily contiguous. `preadv` takes a list of memory buffers and fills them from a contiguous range in the file, so 16 adjacent pages can become one 128 KiB read instead of 16 reads of 8 KiB.

The beauty of read streams is that it lets the scan choose the next block through a callback. Postgres collects blocks by looking ahead, and then combines the adjacent ones up to the limit of `io_combine_limit` in Postgres 18.

But there's a case where those adjacent blocks are split into multiple reads: when one page is already in shared buffers. Postgres doesn't need to read that page from disk, so it stops reading from disk when it reaches the page that is in the buffer, and starts another read after it. From [bufmgr.c](https://github.com/postgres/postgres/blob/2f613719fa4eb47b0319f899220511465c5a55da/src/backend/storage/buffer/bufmgr.c#L1366):

> Otherwise we already have an I/O to perform, but this block can't be included as it is already valid.  Split the I/O here.

So we want pages 0 to 15, but page 8 is cached. Instead of one read, we now have a read for pages 0 to 7, a cache hit, and another read for pages 9 to 15. We read fewer bytes, but send two requests. The worst case scenario is when you have every other page cached - now the same range needs eight separate 8 KiB reads.

Combining reads and issuing them asynchronously solve different problems. Combining reduces the number of requests while async I/O lets Postgres start a read before it needs the result, keeping other reads in flight while it processes earlier pages. This was already part of Thomas's [2023 proposal](https://www.postgresql.org/message-id/CA+hUKGJkOiOCa+mag4BF+zHo7qo=o9CFheB8=g6uT5TUm2gkvA@mail.gmail.com): read streams would first provide larger synchronous reads, while giving scans an API that could later use async I/O without changing again - the infrastructure for async I/O arrived in [Postgres 18](https://www.postgresql.org/docs/18/release-18.html)

Andres Freund made a comment about this case in January 2025. He [called it](https://www.postgresql.org/message-id/bgixmidc73doecg7wskq3k76g3nqnglqub7irbrwp4ppjsx43j%40fwre2x775mcl) "the - very common - case of a bunch of "buffer misses" followed by a "buffer hit"". A month later, Thomas [described the split](https://www.postgresql.org/message-id/CA%2BhUKGK_%3D4CVmMHvsHjOVrK6t4F%3DLBpFzsrr3R%2BaJYN8kcTfWg%40mail.gmail.com) with an example:

> For example, if you ask to read 8 blocks, and the 6th one turns out to be a hit, ie already valid in the buffer pool, then we only need to read the first 5 from disk. Perhaps the 7th and 8th blocks will also need I/O, but we don't want StartReadBuffers() to start *two* I/Os, so the 6th block terminates our search.

In the same email, Thomas proposed keeping those extra buffers pinned and passing them back to `StartReadBuffers` on the next call, that way Postgres wouldn't have to unpin them and look them up again just because the read was split. The cached page would still break the read into separated requests, but handling the split would involve less work.

In April 2026, Andres [changed how far ahead a read stream looks](https://www.postgresql.org/message-id/E1w85Nq-002Wi5-1b@gemulon.postgresql.org). Before, each hit reduced the look-ahead distance by 1, while each miss doubled it. With that rule, "a miss followed by a hit will never have the distance grow beyond 2". In a [thread about index prefetching](https://www.postgresql.org/message-id/f3xxfrkafjxpyqxywcxricxgyizjirfceychyxsgn7bwjp5eda%40kwbduhy7tfmu), he also posted a WIP patch to separate two decisions previously controlled by a single internal look-ahead distance: how far ahead to issue I/O, and how far ahead to look for blocks to combine into one read.
