+++
date = 2026-04-03
title = "What /proc sees in 19 MiB"
labels = ["post"]
subjects = ["memory"]
+++

A few weeks ago [I profiled a Node.js server](/pmem/) with recurring memory spikes. I found out dirty pages, allocator behavior and memory that never came back. To build a cleaner mental model, I stripped the problem down to something smaller: python3 -m http.server. 

```
root@debian:/# ps aux | grep http.server | grep -v grep
root       479226  0.0  0.1  32104 19324 pts/1    T    16:10   0:00 python3 -m http.server
```

19 MiB of resident memory. Where is every byte?

To answer that, it helps to know that memory is managed in three layers, and each one has its own view of what's "used."

- The application allocates objects - strings, buffers, structs. When it calls free() or the garbage collector runs, the object is gone from the application's perspective.

- The allocator (glibc's malloc) sits between the application and the kernel. It requests pages from the OS in bulk and slices them into chunks. When the application frees an object, the allocator reclaims the chunk but usually keeps the page - it expects the application to allocate again soon.

- The kernel sees pages. A page is mapped or not, resident or not, dirty or clean. When the kernel reports Rss, it counts every resident page, including the ones the allocator is holding empty.

Each layer has its own perspective of what's "free". This post is mostly about the kernel's point of view - but it's impossible to talk about memory without touching the other two layers.

The kernel exposes everything it knows about a process's memory in /proc/pid/maps. Each line is a region of virtual memory that the kernel allocated for this process.

```
00400000-00420000 r--p 00000000 103:02 935097    /usr/bin/python3.13
00420000-0073f000 r-xp 00020000 103:02 935097    /usr/bin/python3.13
0073f000-009f2000 r--p 0033f000 103:02 935097    /usr/bin/python3.13
009f2000-009f3000 r--p 005f1000 103:02 935097    /usr/bin/python3.13
009f3000-00a84000 rw-p 005f2000 103:02 935097    /usr/bin/python3.13
00a84000-00af8000 rw-p 00000000 00:00 0
1d84f000-1dabc000 rw-p 00000000 00:00 0          [heap]
7fae4cd9f000-7fae4cf05000 rw-p 00000000 00:00 0
...
7fae4e03f000-7fae4e067000 r--p 00000000 103:02 920382    /usr/lib/x86_64-linux-gnu/libc.so.6
7fae4e228000-7fae4e235000 rw-p 00000000 00:00 0
...
(8 more shared libraries, same pattern)
...
7fae4e37b000-7fae4e37d000 r-xp 00000000 00:00 0          [vdso]
7fae4e37d000-7fae4e37e000 r--p 00000000 103:02 920377    /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2
...
7fae4e3b4000-7fae4e3b5000 rw-p 00000000 00:00 0
7ffca9328000-7ffca9349000 rw-p 00000000 00:00 0          [stack]
```

Every line follows the same format: an address range, permissions, an offset, a device, an inode, and sometimes a filename. Some lines point to files on disk (libssl.so.3, for example). Others are anonymous (like `7fae4e374000-7fae4e375000 rw-p 00000000 00:00 0`).

The first line[^firstline]:

```
(1)00400000-00420000 (2)r--p (3)00000000 (4)103:02 (5)935097    (6)/usr/bin/python3.13
```

The binary (python3.13) appears 6 times in maps with different permissions and offsets. Each region of the file that needs different permissions (read-only data, executable code, read-write globals) gets its own VMA. The shared libraries follow the same pattern. But who loaded them?

## Shared libraries

[The dynamic linker](https://tldp.org/HOWTO/Program-Library-HOWTO/shared-libraries.html). readelf -l reveals his name:

> [Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]

There's a program header called INTERP, which points to /lib64/ld-linux-x86-64.so.2. This is a real program. You can run it directly, and if you do it will call you a strange lad, then tell you what it does:

> You have invoked 'ld.so', the program interpreter for dynamically-linked ELF programs. Usually, the program interpreter is invoked automatically when a dynamically-linked executable is started.

When the kernel loads python3, it doesn't jump to python3's entry point. It finds the INTERP header, maps the dynamic linker into memory, and jumps there first. The linker opens each shared library, mmap's their LOAD segments (creating the VMAs we see in maps), resolves symbols, and only then jumps to python3's actual entry point.

If you're interested in how the ELF loading sequence works end to end, I found this [lwn article](https://lwn.net/Articles/631631/) really good.

The binary declares its dependencies explicitly:

```
root@debian:~# readelf -d /usr/bin/python3.13 | grep NEEDED
 0x0000000000000001 (NEEDED)             Shared library: [libm.so.6]
 0x0000000000000001 (NEEDED)             Shared library: [libz.so.1]
 0x0000000000000001 (NEEDED)             Shared library: [libexpat.so.1]
 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]
```

The linker reads this list and loads them all before python3's code runs. 

One thing worth noticing: ldd shows 5 libraries, and our maps output had 8 more - libssl, libcrypto, libbz2, and their Python wrappers. Those were loaded later, at runtime, via [dlopen()](https://man7.org/linux/man-pages/man3/dlopen.3.html) - when Python imported modules like ssl or lzma. The linker handles startup dependencies and dlopen handles runtime dependencies.

## Anonymous memory

/proc/pid/maps also show lines with no file at all:

```
00a84000-00af8000 rw-p 00000000 00:00 0
1d84f000-1dabc000 rw-p 00000000 00:00 0          [heap]
7fae4cd9f000-7fae4cf05000 rw-p 00000000 00:00 0
```

Anonymous memory is the expensive kind. A file-backed page can be evicted from RAM and reloaded from disk because the file is still there. An anonymous page has no backing file. If the kernel needs to reclaim it, the only option is swap. If there's no swap, the page stays in RAM until the process frees it or dies.

There's another layer to this. The kernel works in 4 KB pages, but applications allocate in smaller chunks. When python3 allocates a 32-byte string, glibc's malloc takes those 32 bytes from a 4 KB page it already owns. When the string is freed, malloc reclaims the 32 bytes internally but doesn't return the page to the kernel. The kernel still sees a Private_Dirty page with a valid PTE. It has no idea that most of the page is free.

This is why Rss stays high after load drops. The application freed its objects. The allocator reclaimed the space. But the pages are still mapped, still resident. The memory "never comes back" because the allocator can choose not to return free chunks to the operating system.

Despite the differences between the kernel and libc point of view, you can actually see the allocators perspective of resident bytes and used bytes. malloc_stats(3) is the tool we need:

```
root@debian:~# gdb --batch --pid 479226 -ex 'call (void)malloc_stats()'
0x00007f1f94435687 in ?? () from /lib/x86_64-linux-gnu/libc.so.6
Arena 0:
system bytes     =    2543616
in use bytes     =    2215952
Total (incl. mmap):
system bytes     =    3362816
in use bytes     =    3035152
max mmap regions =          4
max mmap bytes   =    1028096
```
3.3 MiB held by the allocator, 3 MiB actually in use. The rest is free chunks the kernel still counts as resident.

## The page cache

Shared libraries are "shared." But shared with whom, exactly?

```
root@debian:~# cat /proc/479226/smaps_rollup
Rss:               19324 kB
Pss:               14879 kB
Shared_Clean:       4988 kB
Private_Clean:      4840 kB
Private_Dirty:      9496 kB
```

Shared with every other process that uses libc, libm, libz. When the kernel loads libc's .text segment, it doesn't give the pages directly to the process. It puts them in the page cache, which is a system-wide cache of file contents, and points the process's page table at those cached pages. If another python3 starts, its page table points to the same physical frames. There is one copy of libc's code in RAM, and it is used by everyone.

But Rss doesn't know this. It counts every physical page mapped into the process. If libc's .text is 1.4 MiB and ten processes use it, all ten report that 1.4 MiB in their Rss. The same physical memory is counted ten times. Pss tries to fix this by dividing shared pages across processes - that's the 4.5 MiB gap between Rss (19 MiB) and Pss (14.8 MiB).

So when someone asks "how much memory is this process using?", the honest answer is: it depends on what you mean by "using". Kill this python3, and what actually comes back? The Shared_Clean pages stay because other processes still reference them. Private_Clean (4.8 MiB) gets reclaimed, it's file-backed but only this process had them mapped. Private_Dirty (9.4 MiB) gets reclaimed - heap, mmap, .bss, anonymous, no one else is referencing them. You get back roughly 14.3 MiB. 

## Virtual vs physical[^gorman]

So the binary, the shared libraries, and the anonymous regions are all mapped and the kernel created VMAs for all of them. But creating a VMA doesn't cost any physical memory. The kernel reserved address space. Did it actually put anything in RAM?

Remember the ps aux output?

```
root@debian:/# ps aux | grep http.server | grep -v grep
root       479226  0.0  0.1  32104 19324 pts/1    T    16:10   0:00 python3 -m http.server
```

32104 is VSZ, the process' virtual size. 19324 is Rss, the process' resident set size. 32 MiB of virtual address space, but only 19 MiB actually in physical RAM. Where's the other 13 MiB?

Nowhere. It doesn't exist yet.

Every address in maps is virtual. When the kernel creates a VMA for libm's .text, it reserves a range of virtual addresses. But the page table entries are empty since no physical were frames allocated yet.

The first time the CPU accesses an address in that range, the MMU tries to translate the virtual address to a physical one, finds no page table entry, and raises a page fault. The kernel handles it by allocating a physical frame, loading the data from disk (or finds it already in the page cache), creating the page table entry. Then the CPU retries. Now that page is resident and it counts toward Rss.

This is demand paging. The kernel promises address space without backing it with physical memory. A 1 GB shared library mapped into your process adds 1 GB to VSZ. But if you only call one function, Rss grows by maybe 4 KB - one page.

The gap between VSZ and Rss is all the virtual address ranges that exist but haven't been touched yet - or were touched and then evicted. VSZ is what the kernel promised, Rss is what's actually in RAM right now.

## The special ones

Three VMAs left at the bottom of maps:

```
7fae4e377000-7fae4e37b000 r--p 00000000 00:00 0          [vvar]
7fae4e37b000-7fae4e37d000 r-xp 00000000 00:00 0          [vdso]
7ffca9328000-7ffca9349000 rw-p 00000000 00:00 0          [stack]
```

[stack] is the process's call stack - function arguments, local variables, return addresses. 132 KB.

[vdso] (virtual dynamic shared object) is a small library the kernel maps into every process. It lets the process call things like gettimeofday and clock_gettime without entering the kernel - the code runs in userspace, reading from [vvar]. Fast path for syscalls that get called thousands of times per second.[^vdso]

## 19 MiB

Rss is 19 MiB. That's what ps reports, what kubectl top shows, what your OOM limits use. It's a conservative number: it counts everything mapped and resident, including shared pages.

Most of the time, that's enough. But when memory behaves oddly - Rss grows and doesn't drop, or OOMs don't line up with expectations - the number alone isn't enough.

Part of those 19 MiB is shared library code that exists once in RAM no matter how many processes map it. Part of it is allocator-held memory the kernel still counts as used. The portion that actually goes away when the process dies is smaller - about 14.3 MiB here.

The breakdown is in /proc/pid/smaps_rollup.

[^load]: The "What's in it" column comes from the ELF section-to-segment mapping in `readelf -l`:
    ```
       02     .note.gnu.property .note.gnu.build-id .interp .gnu.hash .dynsym .dynstr .gnu.version .gnu.version_r .rela.dyn .rela.plt
       03     .init .plt .text .fini
       04     .rodata .stapsdt.base .eh_frame_hdr .eh_frame .note.ABI-tag
       05     .tdata .init_array .fini_array .dynamic .got .got.plt .data .PyRuntime .probes .bss
    ```

[^relro]: GNU_RELRO (RELocation Read-Only). This prevents an attacker from overwriting function pointers in the GOT. Found this interesting article from Red Hat: https://www.redhat.com/en/blog/hardening-elf-binaries-using-relocation-read-only-relro

[^gorman]: I will introduce a bunch of new concepts in a few lines. They are hard to understand. This post won't cover them because I plan to write about zones, regions, etc, in another post. The best resource I found so far is the "Understanding the Linux Virtual Memory Manager", by Mel Gorman. Check out: https://www.kernel.org/doc/gorman/html/understand/index.html. Keep in mind that Gorman works on kernel 2.6. This is an old version, and some things may not be updated. This is highly recommended as a foundational work, though.

[^vdso]: See `man 7 vdso` for details. The vdso avoids the overhead of a full syscall (context switch to kernel mode and back) for frequently called, read-only kernel data like the current time.

[^firstline]: `00400000-00420000` is a range of virtual addresses. r--p is the permissions: readable (r), not writable (-), not executable (-), private (p). `00000000` is the offset into the file. `103:02` is the block device (major:minor). `935097` is the inode - the file's identity on disk. And /usr/bin/python3.13 is the file.

