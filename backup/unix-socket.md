+++ 
date = 2025-05-15
title = "Exploring socat(1) and unix sockets"
+++

I was just trying to have a nice, quiet day when I opened Jan's [Advanced Programming in Unix the Environment course](https://www.youtube.com/playlist?list=PL0qfF8MrJ-jxMfirAdxDs9zIiBg2Wug0z), specifically in the lecture about stat(1). While watching the part about `st_mode` and file sharing, I came to the realization that a socket is also a file type (or only a type in the mode field?)[^1].

This blew my mind a bit. I've used TCP sockets plenty - you know, `localhost:8080` and all that. But Unix sockets? These are actual files sitting in your filesystem that you can `ls` and `stat`. Let me create one and see what's up:

```
➜  ~ socat - UNIX-LISTEN:/tmp/test.sock &
[1] 12345
```

Now I have a socket file at `/tmp/test.sock`. Let's examine it:

```
➜  /tmp stat test.sock
  File: test.sock
  Size: 0               Blocks: 0          IO Block: 4096   socket
Device: 259,3   Inode: 14155790    Links: 1
Access: (0755/srwxr-xr-x)  Uid: ( 1000/   frnsh)   Gid: ( 1000/   frnsh)
```

Cool! So it shows up as type "socket" in the filesystem. This is fundamentally different from TCP sockets - those live in kernel networking tables, not as files you can find with `ls`. This socket file is sitting right there in `/tmp` like any other file.

Let's see if I can interact with it like a regular file:
```
➜  /tmp cat test.sock
cat: test.sock: No such device or address
```

Nope! I can't `cat` it like a regular file. What about other shell utilities?

```
➜  /tmp echo "hello" > test.sock
bash: test.sock: No such device or address
```

Can't write to it either. So this "file" behaves completely differently from regular files. It's there in the filesystem, but it's not a data container - it's something else entirely.

Now let's actually use it as a socket:

```
# Terminal 1
➜  ~ socat - UNIX-LISTEN:/tmp/test.sock

# Terminal 2  
➜  ~ socat - UNIX-CONNECT:/tmp/test.sock
```

Perfect! I can send messages between the terminals. From the client, I send `Hello from unix-connect!` and it appears on the server side. Communication works perfectly.

But here's the weird part: I just sent data through this socket file, yet...

```
➜  /tmp stat test.sock
  File: test.sock
  Size: 0               Blocks: 0          IO Block: 4096   socket
```

The file size is still 0. The data isn't stored in the file itself - it's just passing through the kernel's socket mechanism. The file is more like a "meeting point" or "address" that processes use to find each other.

Let's see what system calls are happening when I use `socat`:

```
...
openat(AT_FDCWD, "/lib/x86_64-linux-gnu/libresolv.so.2", O_RDONLY|O_CLOEXEC) = 3
read(3, "\177ELF\2\1\1\0\0\0\0\0\0\0\0\0\3\0>\0\1\0\0\0\0\0\0\0\0\0\0\0"..., 832) = 832
read(6, "hello from UNIX-CONNECT:/tmp/tes"..., 8192) = 39
write(1, "hello from UNIX-CONNECT:/tmp/tes"..., 39hello from UNIX-CONNECT:/tmp/test.sock
```

Ah! When I send a message through the socket, we can see actual `read` and `write` system calls. This clarifies why the socket file has an IO Block - it needs to know the chunk size for data transfers.

So socket files are weird: they live in the filesystem like regular files, but you can't interact with them using normal shell utilities like `cat` or `echo`. They're special files that only work with socket APIs. The file is just an "address" in the filesystem - the actual communication happens through kernel buffers, not file storage.

That's pretty cool! You get the benefit of filesystem-based addressing (no need to remember port numbers), but the performance of direct kernel communication.


[^1]: I found out that type and mode are two different and identifiable things: 
    ```
    ➜  ~ stat -c "%F %f" /tmp/test.sock
    socket c1ed
    ```

    %F is the type, while %f is the mode. 
