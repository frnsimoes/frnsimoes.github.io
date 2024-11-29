+++ 
date = 2024-07-28
title = "TCP reliable delivery"
categories = ["networks"]
+++

"Reliable delivery" is one of the central and most interesting subjects of the transport layer. The meaning of "reliable" was defined in [RFC793]:

> The TCP must recover from data that is damaged, lost, duplicated, or delivered out of order by the internet communication system. This is achieved by assigning a sequence number to each octet transmitted, and requiring a positive acknowledgment (ACK) from the receiving TCP. If the ACK is not received within a timeout interval, the data is retransmitted. At the receiver, the sequence numbers are used to correctly order segments that may be received out of order and to eliminate duplicates. Damage is handled by adding a checksum to each segment transmitted, checking it at the receiver, and discarding damaged segments.

> As long as the TCPs continue to function properly and the internet system does not become completely partitioned, no transmission errors will affect the correct delivery of data. TCP recovers from internet communication system errors.

ACKs and Seq are features used to make segment delivery reliable. This topic is quite broad, and the problems that can arise during communication and packet (or segment) transmission are quite varied and complex. The RFC mentions some when it says that TCP must be able to recover in cases of: 1. corrupted data; 2. lost data; 3. duplicated data; 4. data delivered out of order.

Let's suppose a practical scenario: we have a server and a client. The client's socket sends three segments to the server's socket: A, B, and C. These segments reached a router that had a full buffer. The server's socket received segment A, lost segment B (due to the full buffer), and then "received" segment C.

The problem is that the server's socket process cannot process segment C immediately because B is an essential part of the complete message. The desired outcome is for the server's kernel to buffer segment C until segment B arrives. (Think of "the data" as just one, and the segments as partitions of that data).

We also need a retransmission mechanism for segment B. Right? Because it needs to be resent. Communication cannot end just because the router's buffer was full and segment B was not successfully delivered.

Therefore, we need:

- The client to inform the server that segment B was not received.
- A mechanism that allows the server to infer that if there was no ACK from the client for a segment, that segment was probably lost.
- Ensure the order of receipt. It may be that segments B and C did not take the same path between the links.
- Avoid receiving duplicate segments.

I don't want to write about all these points in this text, but reflect a little on ACK and Seq, two fields of the TCP Header.

TCP implements the notion of sequence number (seq #), linked to the size of the previously received bytes. When a TCP connection is established, the client and server agree on the sequence number for the initial packets, known as ISN (Initial Sequence Number)[^1]. Therefore, if the last segment contained seq: 10,000, the next sequence number will be based on the size of the previous segment's data.

A simple example is when a segment is sent with a size of 1000 bytes. In this scenario, we have the following, in a simplified manner:

```
Send: segment 1: seq = 1001, data = 1000 (bytes)
Receive: ack = 2002
```

This means that the server received segment 1, verified that the data is 1000 bytes, and now awaits the segment with seq = 2001.

[RFC793] talks about "data offsets," a field in the TCP header that indicates where the data begins. The receiver's kernel uses this field to check the next expected length based on the size of the already received segment.

> The number of 32 bit words in the TCP Header. This indicates where the data begins. The TCP header (even one including options) is an integral number of 32 bits long.

Now, what is ACK? ACK is the number that represents, on the receiver's part, everything that has already been received by it. Suppose, therefore, that the server received, from a client, up to byte 12,000. In this case, the last request will contain an ACK of 12,001. From the same RFC:

> If the ACK control bit is set this field contains the value of the next sequence number the sender of the segment is expecting to receive. Once a connection is established this is always sent.

Returning to the initial example where segment B is lost:
- Segment A has data of 1500 bytes.
- The receiver assumes that segment B will go from 1501 to 3000
- The receiver receives C, with offset at 3001
- The ACK of the response, in the TCP header, will be 1501 (comprising only the acknowledgment of the first 1500 bytes of segment A and indicating that the next expected is 1501)

Another interesting topic is the following question: how long does the socket that sent the segment wait for the ACK until it decides to resend it, assuming it was lost?

One way to measure this time is to use the first handshake as a measure of the expected time in the "roundtrip." The roundtrip time includes both the outbound and return times. The problem is that RTT is influenced by various factors (distance between links, for example, or the number of clients). Therefore, another interesting measure is to measure the variation of the various RTTs.

Therefore, returning to the problems mentioned at the beginning: Seq and ACKs are enough to: correctly reorder out-of-order received segments, as each segment has a unique sequential number. The absent ACK indicates to the client that a particular segment was not received, causing it to retransmit the data; and duplicate data is discarded based on sequence numbers and checksum.
```

[RFC793]: https://www.ietf.org/rfc/rfc793.txt

[^1]: The sequence number in the header is the first octet in the segment, except when the SYN is present in the header.
