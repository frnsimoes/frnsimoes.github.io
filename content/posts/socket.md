+++
date = 2024-09-01
title = "What does it mean to bind to a port?"
tags = ["OS theory and fun"]
+++

The socket implementation is a really messy thing to do by hand. Parsing bytes and saving states of a network communication is a tremendous work, but every piece of software that is an abstraction over the network must create its own socket abstraction or use an existing one[^1].

Sockets are so fundamental to networking communication because a network application typically consists of a pair a programs - a client program and a server program - residing in different end systems.[^2]

When the client's socket sends something to the server's socket, what it is doing is actually this:
- The client operating system has a running process with a socket created;
- The server operating system creates a running process with a socket;

This simple behavior must have been amazing to those who were creating this mechanism. If we think about it, we are saying that: there's a machine, a physical machine, that is running something. And there is another machine, maybe in other parts of the world, that is running another something. They both can communicate, having a common a protocol and exchange messages. How amazing is this? If even inside the same operating system there are so many dificulties of inter-process communication. The ability for two processes, potentially thousands of miles apart, to communicate is indeed a marvel.

But how does the client socket knows where the server socket is? Unix systems use the `bind`[^3] system call. The signature of `bind` is something like this: `bind(file_descriptor, (address, port))` When a socket is binded, what it really does is associate a file descriptor (that is just an integer) to the address and port. The port is where the server process is really running at the server machine. 

The file descriptor part is maybe hard to understand. But what it means is not that complicated: a file descriptor is an integer that uniquely identifiesd an open file (or socket) within a process. When a process open a file or creates a socket, the OS assigns a file descrip[tor to represent that resource. The OS uses the file descriptor to handle the communication, including handling the data exchange (read and write). The OS also uses the file descriptor to keep track of active network connections and ensure data is directed to the correct process.

**But what is a file descriptor?**

Understanding how file descriptors work can be challenging, though. And I have taken sometime to understand it more. A file descriptor is something stored in the "File descriptor table". This table is stored within the address space of each individual process. So, when a process open a file, or creates a socket, the kernel assigns a file descriptor to represent that resource. `Process 1 -> Address Space -> (Heap, Stack, text segment, data segment, ... file descriptor table, ...).`

Imagine that:
1. User opens a file -> A file descriptor (say, integer "42"), is associated with it.
2. User writes to file -> the OS knows what file it is because it can fetch from the file descriptor table what is the file associated with the file descriptor `42`.

This process could be represented somehwat like this:

```
int fd = open("file.txt", O_WRONLY | O_CREAT, 0644);
write(fd, buffer, sizeof(buffer));
```

[^1]: See, for example, Go's http package implementation: https://github.com/golang/go/blob/master/src/net/internal/socktest/switch_posix.go
[^2]: James F Kurose_ Keith Ross - Computer Networking: A Top-Down Approach-Pearson
[^3]: `man 2 bind`: bind() assigns a name to an unnamed socket.  When a socket is created with socket(2) it exists in a name space (address family) but has no name
     assigned.  bind() requests that address be assigned to the socket.

