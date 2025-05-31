---
Title: "Forcing a TCP overflow"
Date: 2024-05-15
---

### TCP and buffer overflow

I'm just curious to produce a buffer overflow on TCP. What would happen, at the kernel level, when we send 1MB of data to a socket with a receiving buffer of 128 bytes? This is actually a neat way to understand how TCP handles flow control.

Let's check it out:

Our server is simple and direct, very similar to the one we used in the [sockets] article:

```
 import socket

 s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
 s.bind(('localhost', 8000))
 s.listen(1)

 while True:
     conn, addr = s.accept()
     print(f"Connected by {addr}")
     while True:
         data = conn.recv(124)
         print("Receiving data")
```

In this server, we don't close the connection nor send a response to the client. The receiving buffer is tiny (124 bytes) compared to what we'll throw at it.

Our malicious client:

```
import socket
data = b'X' * 1024 * 1024  
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(('localhost', 8000))
client.sendall(data)
```

First run the server, then let's watch what happens in real time:

```
➜  ~ watch -n 0.5 "netstat -an"
```

When you run the sending socket, something interesting happens. The Send-Q (sending queue) in netstat starts filling up. TCP has this brilliant flow control mechanism where it won't let the sender overwhelm the receiver. Let's see this in action:

```
➜  ~ netstat -an | grep 8000
tcp        0    131072    127.0.0.1:8000    127.0.0.1:52431    ESTABLISHED
```

What's actually happening under the hood? The kernel maintains a buffer for each socket (we can see it in /proc/sys/net/core/wmem_default). When this buffer fills up, TCP's flow control kicks in. The receiver starts advertising a smaller window size in its ACK packets, telling the sender "hey, slow down!"

We can actually see the communication between sender and receiver using tcpdump:

```
➜  ~ sudo tcpdump -i lo port 8000
14:23:45.789012 IP localhost.52431 > localhost.8000: Flags [P.], seq 1:1024, len 1023
14:23:45.789013 IP localhost.8000 > localhost.52431: Flags [.], ack 1024, win 5840
...
```

See how the window size (win 5840) gets advertised back? This is TCP saying "I can only handle this much right now."

So our "buffer overflow" attempt actually shows us something beautiful about TCP: it's self-regulating. The kernel handles the heavy lifting of flow control, protecting both sender and receiver from overwhelming each other. This is why TCP is a reliable protocol.

Next time someone tells you they're going to overflow your TCP buffer, you can smile knowing the kernel has your back!


[sockets]: sockets
