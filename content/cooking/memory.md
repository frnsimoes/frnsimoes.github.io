

I like how Tanenbaum starts his chapter on virtual memory. He approaches the memory problem by worrying about how much space a program occupies in memory. One curious thing that he mentions is how early computers didn´t use any kind of memory abstraction or virtualization; each program only saw the physical memory, so two programs couldn't run at the same time - if they did, program 2 could override a memory location of program 1, and then both would eventually crash. I tried to create a simple program to emulate this behavior using mmap: program 1 writes to memory; program 2 overrides the memory location and program 1 crashes. It's a fun experiment. 

The implementations that come after this seem wacky. Swapping was never really good enough - saving the program content to a non-volatile storage like hhd or ssd - because it is slow. Base and bounds occupied too much space because of the necessity of contiguous space and the fact that heap and stack grow in opposite direction - causing the inevitable non used space between them in memory.

Then we had segmentation that achieve multiple base/bounds instead of only one base/bounds. It got better, because now we have small spaces that need to be contiguous, and not big spaces that have too much waste. But segmentation didn´t solve the waste problem, since inside each segment there was non used memory. Segmentation also had another problem: if a big chunk of data came in to that particular segment, it needed to be compacted or rejected (for size reasons).

Fragmentation and the need of choosing between two drastic options (reject or compact) were the main reasons for dissatisfaction with segmentation and the idea of paging. Paging is the idea of diving notionally (ideally?) the address space in blocks. With paging, we have this idea that we can divide (in abstraction) the physical memory in small blocks of 4kb, and then map these blocks in physical memory to 4kb blocks in virtual memory. 

The problem with this idea is that now we need to deal with the "map" part between physical and virtual memory. And how do we do the mapping? By translating it. This translation is handled by the Memory Management Unit (MMU), which uses a data structure called the page table to keep track of the mapping between virtual pages and physical frames.

Dang. Now we have to worry about lookups. 
