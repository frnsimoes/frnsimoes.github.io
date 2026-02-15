+++
date = 2025-10-30
title = "How packet switching won"
+++ 


{{< figure src="/static/packet-switching/telephone.png" alt="A very bad attempt to draw a telephone" caption="" >}}

I don't know why, bt since I discovered about circuit switching, I've been kinda obsessed with what they represented in the history of telecommunications and computer networking. Telecom engineers had to solve a hard problem. In the analog age, carbon microphones converted voice into electrical signals that traveled over copper wires, with amplifiers boosting the signal to maintain quality across distances. In the digital age, the same copper wires remained, but the approach changed: analog signal was sampled at intervals, quantized into bits, and transmited. Both eras needed circuit switching - the strategy to keep two people talking over a dedicated path.

In circuit switching, when host A calls host B, a dedicated path is established through the network: A → switch1 → switch2 → switch3 → B. That path reserves bandwidth - typically 64 kbps for a voice channel[^1]. The switches maintain hard state: which ports are connected, how long the connection has been active, billing information. 

Here's the problem: during a 10-minute call, person A talks for 3 minutes, person B talks for 2 minutes, and there's 5 minutes of silence. The circuit stays reserved for the entire 10 minutes. Those 64 kbps sit there, unusable by anyone else, even during silence. The switches keep tracking the connection, the bandwidth stays allocated, the path remains dedicated.

This worked for voice because we have predictable, continuous streams. The problem is: data is bursty.

You request a webpage and suddenly there is a massive spike of packets. Then nothing while you read for 2 minutes. You send an email - quick burst of a few kilobytes. Then silence. With circuit switching, you'd reserve 64 kbps (or more) for these brief bursts, leaving the circuit idle 95% of the time.

The economic part of this model don't scale. A 1 Mbps link supports exactly 15.625 simultaneous 64 kbps circuits (1000kbps / 64kbps). Want more? Install more infrastructure.

Packet switching redefined this model: it was not dependent on bandwitch reservation. No dedicated paths and no hard state in routers. Instead of having a complicated setup of wires and boxes that needed to keep consuming data without interruption, we now have network devices / interfaces that only needs to know source and destination address, and a few algorithms to calculate routing based on IP prefix. Simple. Beautiful.

When host A sends data to B, it breaks the data into packets. Each packet has source and destination addresses. Packet 1 might go A → R1 → R2 → B. Packet 2 might take a different path: A → R1 → R3 → B. Between packets, the link is free for anyone else to use, because each node is independent.

Routers don't maintain connection hard state. They just: read packet header, check destination address, forward out the correct interface. There is no billing timers, no "port 5 connected to port 12" tracking. Just forward bits.

Intelligence moved to the edges. Hosts handle reliability, retransmission, ordering, congestion control - TCP built at Kernel level is the perfect example of this. The network itself became dumb (or almost, the link layer still have decisions to make).

The infrastructure was already there: copper wires, central offices, physical links. Packet switching won because it used that infrastructure far more efficiently. No need to provision dedicated circuits for every potential connection. Just let everyone share, statistically.

## It took a while

But the transition wasn't instant. For years, packet switching ran *on top of* circuit switching infrastructure.

Remember how, in the 1990s, connecting to the internet meant using a dial-up modem? You'd hear the familiar sequence: dial tone, [DTMF](https://en.wikipedia.org/wiki/DTMF_signaling) tones, handshake negotiation (that beautiful, sober sequence of beeps), then connection[^2]. What was happening?

Your modem was calling the ISP's modem pool - literally making a phone call. The telephone network established a circuit: your house → local exchange → ISP. A dedicated 64 kbps path, just like a voice call. The phone company's switches tracked this as a connection, running billing timers.

But *inside* that circuit, packet switching was happening. Your computer sent IP packets to the modem. The modem modulated those digital packets into [analog signals](https://www.eetimes.com/an-introduction-to-the-v-90-56k-modem/) and transmitted them over the phone line. The ISP's modem demodulated back to digital packets and forwarded them to the internet.

The fun stuff: you were using packet-switched data (bursty web requests, email), but paying circuit-switched rates (billed by connection time) - here in Brazil we would use the dial-up internet on weeks or after midnight so we could pay for only one "tick" -. Even if you weren't transmitting anything - just reading a webpage for 5 minutes - the circuit stayed active and the meter kept running.

The phone company's billing system had no idea you were transmitting data. It just saw: circuit established, duration = 6 hours, charge accordingly. Meanwhile, your actual data usage might have been 10 MB over those 6 hours - mostly idle time.

This hybrid model existed because the infrastructure was telephone lines. The "last mile" to homes was copper twisted pair, owned by telcos, designed for voice circuits. ISPs had to use what existed.

Cable modems did something similar with coaxial cable (TV infrastructure). Fiber eventually replaced both, but the pattern was the same: reuse existing physical infrastructure, gradually shift from circuit-switched billing to packet-switched reality.

The economic model took longer to change than the technology. Packet switching won technically in the 1970s (ARPANET). But consumers didn't get "always-on, flat-rate, packet-switched" internet until the late 1990s/early 2000s - because the business model and physical infrastructure were still tied to circuits.

I remember being amazed when DSL arrived in 2002 - no more waiting for the dial tone, no more fear of the phone bill. The clicks and hisses of the modem disappeared, but in a way, so did a piece of that era.

That’s when I finally understood the beep boop on my dial-up modem, and why packet switching truly won.

---

[^1]:Voice digitization: 8-bit samples at 8 kHz = 64 kbps
    https://dsp.stackexchange.com/questions/22107/why-is-telephone-audio-sampled-at-8-khz

    "Before Bell Telephone started multiplexing voice lines they did a lot of research on the frequency content of the human voice. They developed a band pass characteristic that peaked around 2.1 KHz and rolled off below 300 and over 3000 Hz. That gave a good human sounding voice when done correctly. All that was analog."


[^2]: If you are feeling technical, I highly recommend this blog post: https://www.windytan.com/2012/11/the-sound-of-dialup-pictured.html.
