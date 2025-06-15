+++
date = 2024-04-10
title = "What's the motivation behind persistent connections?"
csp = true
+++


When the web was originally conceive it was Tim Berners-Lee trying to create a management system for documents. This would effectively be research documents with clicable footnotes. Academic documents. It was text based. Make an HTTP request, get an HTTP response. 

This means that for every request and response cycle there is a handshake process. SYN -> SYN/ACK -> ACK -> Request / Response -> FIN -> FIN/ACK -> ACK.

Persistent connections try to end this unnecessary handshake. Modern internet is not only one request / one response. 

HTTP 1.1: Connection: keep-alive

In HTTP 1.1 the header keep-alive became the default.


