+++ 
date = 2023-07-03
title = "What is an HTTP message body?"
+++

An HTTP body is a "stream of data", a sequence of bytes transmitted in the HTTP message[^1]. 

When an HTTP message is sent by the client socket to the server socket, the server socket "receives" the HTTP message from a buffer, which means the receiving socket's recv method (refer to `man recv`[^2]) retrieves data from a temporary storage known as a buffer, which has a finite capacity.

This is as simple as saying something like this: `client_socket = server_socket.accept(); client_socket.recv(4096)`. 

Imagine that the body has, say, 32768 bytes. The receiver socket doesn't know how many bytes the data has, so it has to process that data iteratively until it completes. It will process the data in chunks of 4096 bytes, since, in our case, the socket's buffer has the maximum size of 4096 bytes.

But what do I mean by "sequence of bytes transmitted within the message"? What's "the message"?

In the context of HTTP specifications, a request has fundamentally three elements (there are more ):

- Request Line
- Header Fields
- Message Body

The request line contains a method, a request target, and the HTTP version. For example: `GET / HTTP/1.1`.

The header fields are the headers, which are key-value pairs separated by a colon and optional white spaces (OWS).

The message body, as described by RFC 9110, "is a stream of octets sent after the header section."

How do we know that the Request Line is over? Or that the Header Fields are over? How do we parse these different parts of the HTTP message? They are separated by something as trivial as a CRLF (carriage return line feed: \r\n).

We know that the request line is over because we can check that there is a \r\n, and we know that the header fields are over because there is a double CRLF: `\r\n\r\n`.

For example: `GET / HTTP/1.1\r\nContent-length:5\r\nFoo : bar\r\n\r\n`

Each new header line ends with a CRLF, but the header section itself also ends with CRLF, so we know for sure that when we see a `\r\n\r\n` in the HTTP message, next we are going to see the body: `POST / HTTP/1.1\r\nContent-length:5\r\nFoo : bar\r\n\r\nHello World Body\r\n`

The HTTP body is especially interesting because it is consumed by the receiving socket. So, for example, if the server has read and consumed the body once, it can't read and consume it again. This is the origin, for example, of the Django error "You cannot access body after reading from request's data stream."

In Go, we commonly read the body with the io.ReadAll call. The ReadAll method reads the body (bytes) until EOF (end of file) and returns the data read.

So, let's take a closer look at what it means to read a body.

In [this example](https://github.com/frnsimoes/computer-science-studies/blob/main/network-programming/http/proxy-basic/client.py), the client socket makes a handshake with a proxy, send to the proxy an initial GET request, and then waits for the response, processing it in chunks of 1024 bytes. 

[^1]: If you don't know what I mean by "HTTP Message", try this:

    ```
    # terminal session 1
    python -m http.server 8001
    ```

    ```
    # terminal session 2
    nc localhost 8001
    GET / HTTP/1.1
    Foo:Bar

    ```
[^2]: recv, recvfrom, recvmsg,	recvmmsg -- receive message(s) from a socket

    The recv() function is normally used only on a connected socket (see connect(2) or connectx(2)) and is identical to recvfrom() with a null pointer
