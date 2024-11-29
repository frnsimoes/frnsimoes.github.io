+++ 
date = 2024-07-09
title = "Sockets, select and IO Multiplexing"
categories = ["operating-systems"]
+++

IO multiplexing is a complex topic at first. But it's the basis of "concurrency" without multiple threads or processors. So it's pretty handy. One example of a nice use of IO multiplexing is Redis; another is Nginx.

The secret of IO multiplexing is being able to handle multiple things at once. And by "things" I mean multiple behaviors that have an input or output in file descriptors.

Multiplexing is a well-known resource to deal with the "we need to gather some things, and then deliver them to their own proprietors" scenario. It's a way of diligently proxying receipts to their appropriate recipients.

Multiplexing and demultiplexing are largely used in network protocols at the transport layer. When you use your computer, you don't only connect to one network at a time. Usually, you are listening to music, sending emails, chatting, and downloading files. UDP and TCP know how to handle this and how to deliver the appropriate datagram/segment to the correct socket.

But what if you have only one process, and you want to create this same functionality? Suppose you are a server and want to be able to respond to multiple requests from different origins. What could you do? Well, you could run on multiple threads, or maybe multiple processors. But in many cases, that nor a good option or a possibility.

One way of handling multiple requests in the scope of a single-threaded process is to use IO Multiplexing. In Unix systems, we have the following models of IO:

- Blocking IO model
- Nonblocking IO model
- IO Multiplexing model

**Blocking IO** means that the process will stop its execution until the IO operation completes. **Nonblocking IO**, on the other hand, does not wait for the IO execution to complete; instead, the process continues to run, and, if the IO execution was not completed, it returns an error. 

The IO Multiplexing model is hors-concours, in its turn. It makes use of systems calls like `select`, `poll`, `epoll` (depending on the OS, on my machine with OSX I use `select`, but if you are a linux nerd you can prefer `poll` -- i wish i could) to keep track of file descriptors and handle their readiness of being IOed.

But what does it really mean? How does it really happen? 

Imagine you are a server. Someone sends you a request with `curl`, yet someone else sends you a request with the browser. At first, you don't know what to do. Well, you do, but things are looking good: your socket will process the `curl` request, and the browser request will be blocking potentially by as long as the curl request takes to be executed. 

You don't want that. You are not that kind of server. Are you? You would rather be able to *listen* to the `curl` request, and then, while blocked by it (say it needs some database querying), you want to address the web browser request. 

That's what IO Multiplexing allows you to do.


```
import select
import socket


listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

listener.setblocking(False)

listener.bind(('0.0.0.0', 10000))
listener.listen(10)

inputs = [listener]
outputs = []

to_send = set()

while True:
    readable, writable, excepcional = select.select(inputs, outputs, inputs)
    print('readables')
    print(readable)

    print('writables')
    print(writable)

    for s in readable:
        if s is listener:
            client_sock, client_addr = s.accept()
            client_sock.setblocking(False)
            inputs.append(client_sock)

        else:
            data = s.recv(4096)
            if data:
                print(data)
                outputs.append(s)
                to_send.add(s)
            else:
                s.close()
            inputs.remove(s)

    for s in writable:
        if s in to_send:
            to_send.remove(s)
            outputs.remove(s)
            s.send(b'HTTP/1.0 200 ok \r\n\r\nbody text')
            s.close()
```

Here is what's happening in this ugly code:

This is a TCP connection (identified by socket.SOCK_STREAM). Instead of immediately making the handshake as soon as a client server's request arrive, you call select. What select is going to do is monitor the inputs for you. When the `curl` request arrives, you will receive its message; the same thing goes for the web browser request. They become "readable" because socket (the file descriptor) may wanna read what's been sent by them. 

Note that both `curl` and the web browser request are two different sockets, so they are identified by two different file descriptors. 

When you process the message from the one client, you wanna answer it, that's what the `to_send()` is doing. `writable` is a way of saying: "here is a thing that I want to write to this file descriptor". 

And there you go. While being only one socket, you just created a way of dealing with multiple requests concurrently. 


