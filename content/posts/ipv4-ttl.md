+++ 
date = 2024-09-10
title = "IPv4 TTL is not about time?"
+++

Another interesting historical nerdiness: to prevent packets from getting stuck or looping endlessly between routers, a TTL (time to live) was added to the IPv4 header.

In RFC760 (from 1980!!), the idea of TTL was really about controlling the amount of time a datagram could circulate among routers: with each "hop," the packet's TTL would decrease by the presumed number of seconds that router took to process it.

Consequently, with 8 bits as the maximum TTL value (255), the longest a packet could circulate on the internet would be 4.25 minutes. (Just imagine the discussions this must have sparked...)

RFC791, just a year later, introduced a different perspective. Although the decrement still happens in seconds, the idea of TTL shifted to being an "upper bound" on a datagram's lifespan.

In practice, due to the difficulty of measuring time, each hop simply decrements the IPv4 TTL by 1. This concept also carried over to IPv6, which cleverly renamed the header from "Time to Live" to "Hop Limit."
