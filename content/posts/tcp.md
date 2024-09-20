+++ 
date = 2024-09-13
title = "TCP may be tricky"
+++

TCP may be tricky. Despite having the three-way handshake, TCP also has multiple mechanisms to maintain its reliability. When a client and a server establish a connection and start exchanging data, the two TCP sockets advertise a variable known as the "receive window" (`rwnd`). The receive window indicates the maximum bytes that the TCP socket's buffer can process. Until recent years, the de facto `rwnd` was 64KB. Nowadays, it can be up to 1 gigabyte[^1], depending on server configuration. TCP also has another variable, a private one, called `cwnd`. The purpose of this variable is to avoid congestion. A TCP socket will control how much data it sends over the wire based on this variable. When the client and server start to exchange data, the sending socket checks the `cwnd` variable. If it's the first time it sends data after the three-way handshake, the `cwnd` is set to 10[^2], indicating that the socket can send 10 segments (of ~14KB each). The TCP socket will increase the amount of data sent by doubling it after each ACK. This is called `Slow Start`. Besides Slow Start, TCP also has `Slow Restart`: when the connection is idle for a while, TCP can't presume the state of the network at that moment, significantly reducing the `cwnd` value.

I was reading Ilya's book[^3] yesterday, and in the TCP section, he presents an excellent case study about the time to process a GET request for a 64KB file. The client is in New York, and the server is in London. With the handshake, the total roundtrip time is 264ms. When comparing this value with a request that has an already established handshake, the time drops to a staggering 96ms!

[^1]: Check out RFC 7323 for more details.

[^2]: Since 2013, at least (https://datatracker.ietf.org/doc/html/rfc6928).

[^3]: https://hpbn.co/ - I can't recommend this book enough.
