+++
date = 2024-11-11
title = "A few words about socket tables"
+++

<!-- ![alt](/static/sockets/computer-communication-question.jpg) -->

![alt](/static/sockets/kernel-role-in-tcp-request.jpg)

When a request is received by the machine, the Kernel asks itself: "Hey, do I have a socket file descriptor opened on port 80? Let me check". Then it checks a special table for internet connections: a socket table. We can actually see what's going on there:

```
cat /proc/net/tcp
➜  ~ cat /proc/net/tcp
  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   4: DE01A8C0:0016 7401A8C0:DE24 01 00000000:00000000 02:0006FC06 00000000     0        0 1030697 2 0000000062dd485f 20 4 31 7 7
   5: DE01A8C0:0016 7401A8C0:DE21 01 00000000:00000000 02:0006F94E 00000000     0        0 1030660 2 000000005ddb2235 20 7 31 9 7
```

We don't need to specify the process ID in `/proc/net/tcp` because whether we specify it or not the output will be the same: a list of all tcp connections available in that namespace. It contains both listening and connected sockets, and gives us reference to remote and local addresses (`local_address` and `rem_address`).

After the kernel checks the socket table, it has access to the file descriptor table, in which it tries to find which process that socket is running on. But how does it find the process by identifying the socket? Well, the last information in /proc/net/tcp is the `inode` number. The kernel then finds the process in /proc/pid/fd.

Open a terminal and run a server:

## checking out /proc stuff

```
➜  ~ python -m http.server 8080

Serving HTTP on 0.0.0.0 port 8080 (http://0.0.0.0:8080/) ...
```

On another terminal, find the ID of the process that is running the server:

```
➜  ~ ps aux | grep "python -m http.server 8080" | grep -v grep

frns      168674  0.2  0.0  27752 19644 pts/1    S+   23:58   0:00 python -m http.server 8080
```

Now we can see what file descriptors this process has!

```
➜  ~ ls -l /proc/168674/fd
total 0
lrwx------ 1 frns frns 64 Jan  1 23:59 0 -> /dev/pts/1
lrwx------ 1 frns frns 64 Jan  1 23:59 1 -> /dev/pts/1
lrwx------ 1 frns frns 64 Jan  1 23:59 2 -> /dev/pts/1
lrwx------ 1 frns frns 64 Jan  1 23:59 3 -> 'socket:[1200452]'
```

Let's grep /proc/net/tcp to check the correspondence:

```
➜  ~ sudo cat /proc/net/tcp | grep 1200452
   2: 00000000:1F90 (...) 200452 1 0000000002730145 100 0 0 10 0
```

The important part of the output is the second one: `00000000:1F90` is the hexadecimal for 0.0.0.0:8080.




[read more]: https://www.kernel.org/doc/Documentation/networking/proc_net_tcp.txt
[TCP socket standard]: https://en.wikipedia.org/wiki/Network_socket
[Hamlet]: https://www.folger.edu/explore/shakespeares-works/hamlet/read/
[Everything is a file]: http://ibgwww.colorado.edu/~lessem/psyc5112/usail/concepts/filesystems/everything-is-a-file.html
