+++
title = "Beep boop beep"
date = 2024-10-30
labels = ["post"]
+++

{{< figure src="/static/packet-switching/telephone.png" alt="A very bad attempt to draw a telephone" caption="" >}}

I've been kind of obsessed with packet switching and what it represented in the history of telecom and computer networking. 

In circuit switching, host A calls host B, a dedicated path is established through the network. Data goes through switches and reaches the host. The problem is that that *path* reserves bandwidth, which maintains a hard state. In telephones, it works well: in a 10 minute call, it doesn't matter that the bandwidth was reserved for the whole time, people were talking, the path being dedicated is a requirement for it to work well.

But the same model doesn't fit the internet very well. The internet is bursty, requests are spikes. You request a webpage, then read it for 2 minutes. Later, you send an e-mail. With circuit switching, you would need to reserve 64kbps or more for these brief bursts, leaving the circuit idle for most of the time.

The economics don't scale. Packet switching redefined this model: no more reservation is needed, no dedicated paths, no connection state in routers. Instead of having a complicated setup of wires and boxes, we now have network devices and interfaces that only need to know source and destination addresses, and a few algorithms to calculate routing based on IP prefix. It's simple, and beautiful.

Host A sends data to B, data is broken into packets, each packet has a source and a destination address. Packets are independent and can take different routes. Path is not reserved. 

Routers read packet header, check destination address, forward out the correct interface. It's a dumb task, and it's beautiful because of it. Intelligence moved to the edges, hosts handle retransmission, ordering, congestion control. 

The transition wasn't fast. For years, packet switching ran on top of circuit switching infra. Remember how, in the 1990s, connecting to the internet meant using a dial-up modem? We would hear the familiar sequence of dial tone, [DTMF](https://en.wikipedia.org/wiki/DTMF_signaling) tones, handshake negotiation (that beautiful sequence of *beeps*), then connection[^2]. What was happening?

The modem was calling the ISP's modem pool - it was literally making a phone call. The telephone network established a circuit between your house, a local exchange, and the ISP. Inside that circuit, packet switching was happening. The computer was sending IP packets to the modem, the modem was modulating those digital packets into [analog signals](https://www.eetimes.com/an-introduction-to-the-v-90-56k-modem/) and transmitting them over the phone line. 

The problem was that while we were having fun on IRC we were paying for circuit-switching rate (the dedicated path). Here in Brazil we would use the dial-up internet on weekends or after midnight so we could pay for only one "tick".

The phone company's billing system had no idea we were transmitting data. It just saw that a circuit was established, that the duration was 6 hours, and charged based on that. Meanwhile our actual usage was maybe 10 MB over those 6 hours. This hybrid model existed because the infra was telephone lines. 

Well, I remember being amazed when DSL arrived in 2002 - no more waiting for the dial tone, no more fearing the phone bill. My new modem didn't make that *beep boop* sound, and I didn't know I would miss that sound dearly.

[^2]: If you are feeling technical, I highly recommend this blog post: https://www.windytan.com/2012/11/the-sound-of-dialup-pictured.html.
