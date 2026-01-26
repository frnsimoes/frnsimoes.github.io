+++ 
date = 2024-04-15
title = "cool trick: the kernel stack of a process"

+++

I found a cool trick to see what's happening to a blocked (`sleeping`) process: `cat /proc/pid/stack`. Yep, you can peek at the trace of kernel functions related to a process! 

```
➜  pexpl git:(main) ✗ ps aux | grep p.py
frns       23703  0.0  0.0  13888  7948 pts/3    Sl+  02:48   0:00 nvim p.py

➜  pexpl git:(main) ✗ sudo cat /proc/23703/stack
[<0>] do_epoll_wait+0x698/0x7d0
[<0>] do_compat_epoll_pwait.part.0+0xb/0x70
[<0>] __x64_sys_epoll_pwait+0x91/0x140
[<0>] do_syscall_64+0x55/0xb0
[<0>] entry_SYSCALL_64_after_hwframe+0x6e/0xd8
```

The information I get from this trace is that epoll was called, so the kernel is doing IO multiplexing, probably waiting for a event, and then called a syscall that blocked the process. Combined with other tools, like `strace`, `<pid>/stack` can give an specific perspective of what's wrong with a process. How cool is that?

**about procfs**

`proc` (procfs) is a pseudo-filesystem; it dynamically generate directories for processes. The files within `/proc` doesn't like on disk, similarly to the `/dev` directory. [Wikipedia](https://en.wikipedia.org/wiki/Procfs#History) lists the history of procfs implementation, which goes back to 1984. 
