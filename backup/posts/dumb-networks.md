+++
date = 2025-09-25
title = "Why don't routers guarantee packet delivery?"
+++

I was reading Stevens and something finally clicked in my brain about the history of networks. We begin with circuit switching, an inheritance from telephone network architecture.

Network devices, at this stage, had a lot of work to do: imagine that host A connects to host B. A dedicated path with reserved bandwidth was established through multiple network devices. Their job was to maintain the state of this connection, calculating things like how much time was spent on that connection (for future billing), and who is talking to whom (host identification).

If bandwidth was reserved for a connection, no other connection could use that capacity - even during silence periods. This was wasteful and created scalability problems.

To solve this, we moved to packet switching with stateless forwarding devices. What we now call a "packet" was an entity that had, within itself, the full identification about the source, destination, and other communication details. Forwarding devices use this information to forward packets using best-effort delivery - no guarantees about delivery, ordering, or timing.

This shift moved complexity to the endpoints: TCP (forced adoption in the 80s) at the hosts now handles reliability, flow control, and error recovery - things the circuit-switched network used to guarantee.

We began forcing network devices to know too much. Then we migrated to a "dumb network" model. Also, whenever a packet arrives at a forwarding device and is consumed by the device's buffer, the "wire" that delivered it is freed, eliminating the problem of consumed/occupied bandwidth.

For example, I tracerouted a request to google.com, and my request passed through 21 network devices (21 hops total) to reach its destination. No reserved bandwidth. No waste. Make dumb what needs to be dumb.

## Okay, but what are the responsibilities of the end host? 

Let's investigate a few of TCP's main responsibilities: reliable delivery, ordering, and flow control. The way I'm going to see these concepts in action is really simple: First I'm going to change something on my network using the [`tc`](https://man7.org/linux/man-pages/man8/tc.8.html) utility. Then I'm going to use `curl` to make requests to httpbin.org, and I'm going to use `tcpdump` to capture the packets. Then I'll read the pcap file using `tcpdump -r file.pcap`. You can follow allong.

### Reliable delivery

In circuit switching, the dedicated path guaranteed delivery. With packet switching, TCP must detect and fix losses.

How TCP Detects Loss:

- Timeout-based: If no ACK arrives within RTO (Retransmission Timeout)
- Fast Retransmit: If sender receives 3 duplicate ACKs (same sequence number)

Let's first add some errors to our network using `tc`: 

```
frnsh@debian:~$ sudo /sbin/tc qdisc add dev enp0s1 root netem loss 10%
```

Here is what I'm doing with this command:
- **[qdisc](https://tldp.org/HOWTO/Traffic-Control-HOWTO/components.html)** is a scheduler. It's responsible for queueing.
- **add** means we are installing the new qdisc
- **dev enp0s1** - to the device enp0s1, which is my network interface.
- **root** replace the default root qdisc
- **[netem](https://man7.org/linux/man-pages/man8/tc-netem.8.html)** is the emulation network qdisc
- **loss 10%** means we will randomly drop 10% of outgoing packages.

After this, let's call tcpdump to watch for httpbin.org requests:

```
tcpdump -i any -n -S host httpbin.org -w reliable_delivery.pcap
```

After a few curls, I spotted this on the logs:

```
5 14:28:22.457982 enp0s1 In  IP 34.233.137.169.443 > 10.0.2.15.47688: Flags [.], seq 2101023746:2101026626, ack 4131958569, win 65535, length 2880 [:path: /bytes/10000]
6 14:28:24.065455 enp0s1 In  IP 34.233.137.169.443 > 10.0.2.15.47688: Flags [.], seq 2101023746:2101025186, ack 4131958569, win 65535, length 1440 [user-agent: curl/8.14.1]
7 14:28:27.083498 enp0s1 In  IP 34.233.137.169.443 > 10.0.2.15.47688: Flags [.], seq 2101023746:2101025186, ack 4131958569, win 65535, length 1440
```

The same sequence is being sent again because of our dirty trick with tc qdisc. Also, I noticed something really interesting: the first packet (line 5) has a length of 2880 bytes: the server initially tried to send 2880 bytes, but after the retransmission timeout, it reduced the segment size to 1440 bytes. This is TCP's congestion window shrinking - it assumes network congestion caused the loss and becomes more conservative.

Let's also watch the request with nstat:

```
frnsh@debian:~$ watch -n 0.5 'nstat | grep -E "(Retrans|InSegs|OutSegs)"'
```

The result (couldn't get the full result because it keeps changing):

```
Every 0.5s: nstat | grep -E "(Retrans|InSegs|OutSegs)"                                 debian: Thu Sep 25 14:32:35 2025

TcpInSegs                       24                 0.0
TcpOutSegs                      12                 0.0
TcpRetransSegs                  1                  0.0
```

I gotta say that the change in `qdisc` made my virtual machine REALLY SLOW.

### Ordering

In circuit switching, the dedicated path naturally preserved packet order. With packet switching, packets can take different routes and arrive out of order. TCP must reassemble them correctly.

How TCP Handles Ordering:

- Sequence numbers: Every byte gets a unique sequence number
- Buffering: Receiver holds out-of-order packets until gaps are filled
- Reassembly: Delivers data to application only when contiguous

First, let's do the `tc` trick:

```
frnsh@debian:~$ sudo tc qdisc add dev enp0s1 root netem delay 10ms reorder 25% 50%
```

This command creates qdisc that will reorder packets. This is insane, by the way.

Let's find out what tcpdump captured for us:

```
15:25:37.891709 seq 2049541540:2049541666 (length 126)  # Packet A
15:25:38.033126 seq 2049541806:2049541844 (length 38)   # Packet C 
15:25:38.134826 seq 2049541666:2049541806 (length 140)  # Packet B 
```

The segments sequences are unordered. 

What happened?

- Packet B (seq 1666:1806) got delayed by ~100ms
- Packet C (seq 1806:1844) overtook it
- TCP stack sent them out of order due to the network emulation

TCP's Response (on receiving end):

The server would have received packets in order A → C → B, creating a gap. It would buffer packet C and wait for packet B to fill the sequence gap before delivering the complete data stream to the application.

Well, well, well. Looks like the dumb network delivered packets out of sequence, and TCP had to manage the reordering.

### Flow Control

In circuit switching, bandwidth was pre-allocated so sender couldn't overwhelm receiver. With packet switching, TCP must prevent fast senders from flooding slow receivers.

How TCP Flow Control Works:

- Receive Window (rwnd): Receiver advertises available buffer space
- Sliding Window: Sender can only send data up to the advertised window
- Window Updates: Receiver dynamically adjusts window based on buffer availability

To detect flow control, let's just check how our system has interacted with flow control flags until now:

```
frnsh@debian:~$ ss -i | grep -E "(rwnd|cwnd)"
         cubic rto:268 rtt:58.889/48.551 ato:44 mss:1460 pmtu:1500 rcvmss:1460 advmss:1460 cwnd:10 ssthresh:9 bytes_sent:275497 bytes_retrans:19396 bytes_acked:256101 bytes_received:181409 segs_out:4893 segs_in:9003 data_segs_out:4290 data_segs_in:4903 send 1.98Mbps lastsnd:1032 lastrcv:1032 lastack:1032 pacing_rate 2.38Mbps delivery_rate 81.7Mbps delivered:4029 app_limited busy:73332ms retrans:0/142 rcv_rtt:204929 rcv_space:64273 rcv_ssthresh:47104 minrtt:0.26 snd_wnd:65535 rcv_wnd:46719 rehash:141
```

`rwnd` is the receiving window; while `cwnd` is the congestion window.

Let's check what's happening in this connection:

- snd_wnd:65535 = Send window (how much sender can transmit)
- rcv_wnd:46719 = Receive window (receiver's advertised buffer space)
- rcv_space:64273 = Receiver's total buffer space
- rcv_ssthresh:47104 = Receiver's slow start threshold

A TCP buffer has a buffer size of, normally, 8kb. In this case, the host advertised a receive window of 46719 bytes. 

Kurose explains how this works:

> TCP provides flow control by having the sender maintain a variable called the receive window. Informally, the receive window is used to give the sender an idea of how much free buffer space is available at the receiver. Because TCP is full-duplex, the sender at each side of the connection maintains a distinct receive window. Let's investigate the receive window in the context of a file transfer. Suppose that Host A is sending a large file to Host B over a TCP connection. Host B allocates a receive buffer to this connection; denote its size by RcvBuffer. From time to time, the application process in Host B reads from the buffer. Define the following variables:

> - LastByteRead: the number of the last byte in the data stream read from the buffer by the application process in B
> - LastByteRcvd: the number of the last byte in the data stream that has arrived from the network and has been placed in the receive buffer at B

> Because TCP is not permitted to overflow the allocated buffer, we must have:

> LastByteRcvd - LastByteRead <= RcvBuffer

> The receive window, denoted as `rwnd` is set to the amount of spare room in the buffer:

> `rwnd = RcvBuffer - [LastByteRcvd - LastByteRead]`

> Because the spare room changes with time, `rwnd` is dynamic.

Well, that's a lot. What makes the flow control possible is the buffer implementation in TCP. The send buffer holds data until ACK received. The receive buffer holds out-of-order packets until gaps are filled. 

I said before that 8kb was the default buffer size. But let's check this out:

```
frnsh@debian:~$ cat /proc/sys/net/core/rmem_default
212992
```

The receive buffer on this VM is very large. 

The same applies to the send buffer:

```
frnsh@debian:~$ cat /proc/sys/net/core/wmem_default
212992
```

## Final thoughts

The dumb network delivered packets out of sequence, with losses, and without guarantees. TCP at the endpoints handled all the complexity: reliability, ordering, and flow control. This design scales beautifully because network devices stay simple and fast, complexity is handled where it's needed, and the network core remains stateless and efficient.

"Best-effort" delivery actually makes a lot of sense when you think about the evolution of networks. Packets are sent, and they can be sent again, but we, the network people working on lower layers, won't force you, developer of the protocol layer, to do what we want. You can solve your own problems, we only guarantee a few dumb things.
