+++
date = 2025-08-19
title = "A production incident: zombie sockets"
aliases = ["/gcb/zombie-sockets/"]
+++

{{< figure src="/static/zombie-sockets/body-eater.png" alt="alt" caption="The Body Eater: the magical creature you call when you need your sockets closed." >}}

Last month I just had the most fun time with zombie sockets. It was on my second day at this new job as a platform engineer. A developer approached us saying: "Look, there must be a problem in the infrastructure. Users are getting 502s. I already checked everything. It's not the code."

We weren’t so sure. The service in question processed PDFs and had a pretty funky workflow: download a template from S3, load the PDF into memory, add some stuff, save it, then upload the new version back to S3. Suspicious.

So we bumped the timeout from 1 to 5 minutes. Still timing out. We then proceeded to check the logs, but the exact function that was probably causing the problem (the one that added things to the pdf) had zeros logs. So we added logs, created a PR, triggered the CD pipeline, which in turn created a new revision — a new deploy. Magically, the server came back up. No timeouts. What happened?

For the rest of the day, requests looked perfect. Crisis averted, or so we thought. The very next afternoon the same developer appeared: “Hey, 502s again.” Damn it. After a few painful hours reading the code and the logs, our lead noticed a warning: "Max sockets… 50… 75 sockets in queue."

Immediately, I thought: something is opening a socket but is never closing it. And there it was: the S3 implementation was not consuming the body (meaning: socket.close() was never called), so we had a bunch of open sockets floating around.

The fix was really, really simple: let the client consume the body. A simple request.body.string() is often enough. A simple implementation a body consumption at the socket level may look like this:

```
while True:
    resp_chunk = client_sock.recv(1024)
    if not resp_chunk:
        break

    response += resp_chunk
```

Computers often employ this mechanism for inter-process communication: they use a buffer, and the buffer delivers chunks of data so the client can consume them (think of a big file being delivered over the wire). If chunks are not consumed, the buffer keeps filling up - even worse, imagine the server sent the first 1024 bytes: if the client doesn’t consume this first chunk, the server can’t send the next one because the buffer is full.

Once these chunks are consumed, they cease to exist (this is why you can’t consume a request body more than once). Problem solved. Stream of data fully consumed. With the buffer drained, the server is finally able to close its side of the connection and send a FIN packet.
