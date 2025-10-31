+++
date = 2024-12-08
title = "Notes on paging and other memory stuff"
description = "Exploring memory pages on Linux, especially HUGE_TABLES, copy-on-write"
+++

One of the most practical things we can do on a linux box regarding memory is to use `mmap` to create a new mapping (in the userland!) in the address space of a process. The other day I was playing around and reading the `mmap` documentation when I found a flag named `MAP_HUGETLB`. I got hooked by this and couldn't stop myself from finding out more.

So here it is: A [huge page](https://man7.org/linux/man-pages/man2/mmap.2.html) is a page that is bigger than the default page size of a system. We can actually see these values in a linux machine:

- `getconf PAGE_SIZE` shows the default page size in the operating system.
- `cat /proc/meminfo` has info about the `Hugepagesize`.

In my case, the default page size is `4096` bytes and the `hugepagesize` is `2048kB`.

So, what does `MAP_HUGETLB` do? It requests pages larger than the default page size for memory mappings. This is useful for programs with a large memory footprint. For example, consider a process that uses 2 MB of memory. Using the default 4 KB pages, mapping this memory would require 512 entries in the TLB (Translation Lookaside Buffer). In more costly page table walks, this increases the likelihood of TLB misses. Instead, we can Use a huge page size (e.g., 2 MB), allowing the same memory to be mapped with a single TLB entry, significantly reducing TLB misses and improving efficiency.

### But what are these pages, and why do they have sizes?

The history of memory abstraction implementation in operating systems is both confusing and complex. I like how Tanenbaum mentions that early machines didn't have any kind of memory abstraction; all they could access was the physical memory. Imagine the horror: two programs couldn't run concurrently without crashing because one process could overwrite the memory locations of another. There was no notion of address space.

Before paging, the implementations required memory blocks to be contiguous. The stack and heap grew in direct opposition, leading to inevitable waste of space in the middle of the memory block (I highly recommend OSTEP for studying base-and-bounds and segmentation).

Nowadays, we use paging. The address space is composed of pages of `PAGE_SIZE`. These pages aren't contiguous but are instead mapped. We now use lookups: virtual addresses must be translated into physical addresses. The TLB is a cache that aids in this translation. If the translation is not found in the TLB (a TLB miss), the MMU performs a lookup in the page table (a page walk). This lookup can also fail if there is no available translation for the virtual address. In such cases, the OS sends a segmentation fault signal to the program, which can then handle it or crash.

### What happens when a program is loaded into memory?

When a new program starts, does the OS make available a new and clean memory space for it? If not, does it have to clean the memory space before loading the program?

The answer is: it depends. The OS can make available a new and clean memory space for the program, or it can make available a memory space that was previously used by another program. In the second case, the OS needs to clean the memory space before loading the program. This is done by the OS by zeroing the memory space[^3] before loading the program. This is done to avoid leaking information from the previous program to the new program.

But what happens if that memory was used for some important, sensitive information? After all, we expect the operating system to respect the isolation of processes, right? If a program tries to access memory it does not have permission to access, it will cause a segmentation fault. The OS sends a SIGSEGV signal to the program, indicating an invalid memory access. This ensures that processes remain isolated and do not interfere with each other's memory.

When a program terminates, the operating system's kernel reclaims the memory that was allocated to the program. This means the memory is marked as free and can be allocated to other programs. However, the contents of the memory are not immediately erased. Instead, the kernel ensures that any new program allocated this memory space cannot access the data left behind by the previous program. This is typically achieved by zeroing out the memory before it is allocated to a new program, maintaining the security and isolation between processes.

### What happens when a child process tries to write?

Imagine a simple `fork()`: a bash process originates another bash process, which calls `cat` on a file, for example. In this case, the child process has a copy of the parent process, but both of them are isolated (after all, we are talking about processes); both have their own memory address space in pages[^4].

So, in physical memory (logically) there is a frame that is shared between parent and child. When the child tries to write to this frame, the OS will copy the frame to another location in physical memory, and then the child will write to this new location. To help with some visualization: Imagine physical memory as a box A, and the shared memory between parent and child as a small box X inside the big box A, the OS will copy the content of box X to another box Y, and then the child will write to box Y. This is done to ensure that the parent and child processes remain isolated from each other.

[^1]: A core dump file contains the recorded state of the program. You may need to have permissions to generate the core dump. The file may not be generated in the same directory as the program. Check the contents of `/proc/sys/kernel/core_pattern` to see where the core dump file is generated.

[^2]: `man 7 signal`

[^3]: https://stackoverflow.com/questions/2884230/zeroing-out-memory, this is a good discussion about zeroing out memory in C.

[^4]: This is a great discussion: https://stackoverflow.com/questions/4594329/difference-between-the-address-space-of-parent-process-and-its-child-process-in
