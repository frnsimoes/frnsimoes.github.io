+++ 
date = 2025-05-15
title = "Exploring socat(1) and unix sockets"
+++

I was just trying to have a nice, quiet day when I opened Jan's [Advanced Programming in Unix the Environment course](https://www.youtube.com/playlist?list=PL0qfF8MrJ-jxMfirAdxDs9zIiBg2Wug0z), specifically in the lecture about stat(1). While watching the part about `st_mode` and file sharing, I came to the realization that a socket is also a file type (or only a type in the mode field?)[^1].

So, I first created a unix connection using /tmp/test.sock file. 

```
➜  /tmp stat test.sock
  File: test.sock
  Size: 0               Blocks: 0          IO Block: 4096   socket
Device: 259,3   Inode: 14155790    Links: 1
Access: (0755/srwxr-xr-x)  Uid: ( 1000/   frnsh)   Gid: ( 1000/   frnsh)
```

Ok. IO Block is still there, so it means that socket files still have some operation around reading / writing. 

The socket file itself doesn't actually store any data though. It's essentially an "address" or reference point in the filesystem that processes can use to find and connect to each other. 

Let's actually connect through a socket file to see what happens:

```
# Terminal 1
➜  fun socat - UNIX-LISTEN:/tmp/test.sock

# Terminal 2
➜  fun socat - UNIX-CONNECT:/tmp/test.sock
```

Can we exchange messages? Yes!

From the client, I sent an agreeable and inquisitive message: `Hello from unix-connect?`. The server responded: `Yeah, I can see you, unix-connect. Can you see me? By: unix-listen`. So, yes, both terminals could see the messages they themselves sent, and the messages received. But wwhere *are* the messages? Did the size of the socket file change after sending them?

```
➜  /tmp stat test.sock
  File: test.sock
  Size: 0               Blocks: 0          IO Block: 4096   socket
```

Nope. Let's try to read what's inside the file (I sent some data, so maybe they are stored in the file?)

```
➜  /tmp cat test.sock
cat: test.sock: No such device or address
```

What happened? test.sock IS a file. But it has no size. And I can't cat it? 

This actually makes sense because socket files can't be read directly with standard file I/O operations. The socket is meant to be accessed through socket APIs. The actual data exchange happens in memory buffers managed by the kernel, not on disk.

Let's try to see what's happening when we use socat(1):

```
...
openat(AT_FDCWD, "/lib/x86_64-linux-gnu/libresolv.so.2", O_RDONLY|O_CLOEXEC) = 3
read(3, "\177ELF\2\1\1\0\0\0\0\0\0\0\0\0\3\0>\0\1\0\0\0\0\0\0\0\0\0\0\0"..., 832) = 832
read(6, "hello from UNIX-CONNECT:/tmp/tes"..., 8192) = 39
write(1, "hello from UNIX-CONNECT:/tmp/tes"..., 39hello from UNIX-CONNECT:/tmp/test.sock
```

Oh! When I send a message through the connected socat, we can see the actual `read` and `write`. This clarifies why the socket file has an IO Block. It needs to determine the size of chunks of data it will handle.

So, while socket files do not interact with disks and storage, they require IO Blocks and trigger calls to read(1) and write(1) under the hood. When applications connect to the socket, they're establishing a communication channel through the kernel, not reading/writing to the file directly.

Interestingly, you can even delete the socket file while connections are established, and the existing communication will continue uninterrupted (though new connections couldn't be made).


[^1]: I found out that type and mode are two different and identifiable things: 
    ```
    ➜  ~ stat -c "%F %f" /tmp/test.sock
    socket c1ed
    ```

    %F is the type, while %f is the mode. 
