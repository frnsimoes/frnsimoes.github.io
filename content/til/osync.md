+++
date = 2025-05-18
title = "writing to disk with O_SYNC"
+++

write(2) doesn't actually write to disk imediatelly. Instead, it writes to a page cache and the OS periodically handles writes to disk. Using O_SYNC, though, write(2) returns only when it fully wrote the data to a data block.

Linux exposes the actual timeframe for periodic writings: 

```
➜  ~ cat /proc/sys/vm/dirty_writeback_centisecs 
500
```
