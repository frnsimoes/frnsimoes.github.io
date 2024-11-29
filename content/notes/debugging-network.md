+++ 
date = 2024-09-19
title = "Debugging sessions? Iptables, Docker, etc."
tags = ["debugging"]
categories = ["networks", "experiments"]
+++

Noob me. I spent more than 30 minutes debugging a connection error while trying to access a Postgres server running locally on Docker. I was in the middle of solving another bug, trying to verify some data, and I simply couldn’t connect to the database. Then I remembered I was connected to a VPN, and that was the whole problem. This experience got me really curious (after I finished screaming at the skies in ragged clothes just like King Lear in Act IV). So, what really does happen when we send a request to a server? Let's make this straight and brief, so we can get to the more on point question: Docker.

We are in the application layer, using the internet through a protocol, probably HTTP. HTTP is almost like an external layer that deals with formatting and encoding; its role is to create a contract between client and server. An HTTP request can look like this:

```
POST /user HTTP/1.1
Host: example.com
Content-Type: application/json
Content-Length: 27

{
  "name": "example",
}
```

HTTP’s task is to encode this request message and pass it to the transport layer, which is handled by the operating system kernel. In this case, the transport layer is probably represented by the TCP protocol. TCP receives the encoded message, adds a header to it (with information such as source and destination ports, sequence numbers, checksums, window size, etc.). At this stage, TCP has completed its role in ensuring reliable delivery and passes the message to the next layer: the network layer.

In the network layer, the message is treated as an IP packet, which also has a header and its own mechanisms for routing data. The IP layer is responsible for addressing and routing the packet across networks, ensuring it reaches the correct destination.

Once the IP packet is prepared, it moves down to the data link layer, where it gets encapsulated in a frame that’s ready to be sent over the physical network, where the actual transmission of bits occurs, using electrical signals or radio waves, depending on the medium (e.g., Ethernet or Wi-Fi).

Now, what happens when you try to send a request to a server that is running on your own machine? The whole process changes significantly. Instead, the HTTP encodes the message, passes its binary representation to the operating system, and the Kernel redirects the message internally, looping back the response of the request (hence the "loopback interface" name). The message never leaves the machine. Why? Let's run `ip addr` to check the network interfaces on my machine. The loopback interface is there, and also Docker's bridge network interface:

```
➜  ~ ip addr
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
    inet6 ::1/128 scope host noprefixroute 
       valid_lft forever preferred_lft forever
...

5: docker0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN group default 
    link/ether 02:42:90:57:7c:55 brd ff:ff:ff:ff:ff:ff
    inet 172.17.0.1/16 brd 172.17.255.255 scope global docker0
       valid_lft forever preferred_lft forever
```

What else is there? The network interface of the network card on my machine is there. Also the network interface of the VPN. But what is a network interface? It is a point of interconnection between a computer and a network (be it private or public). There are two main types of network interfaces: the ones that represent physical things, like WiFi and Ethernet; and the ones that represent virtual things, like the loopback and the docker interface.

Thinking about this problem, I decided to access Docker's subnet with traceroute:

```
# VPN disabled
➜  ~ traceroute 172.18.0.2
traceroute to 172.18.0.2 (172.18.0.2), 30 hops max, 60 byte packets
 1  172.18.0.2 (172.18.0.2)  0.123 ms * *

# VPN enabled
➜  ~ traceroute 172.18.0.2
traceroute to 172.18.0.2 (172.18.0.2), 30 hops max, 60 byte packets
send: Operation not permitted
```

Why? Let's try to explore this problem. The book "Docker: Up and running" has a great diagram representing Docker's network:

![alt](/static/docker-net.png)

In this case, the `eth0` (probably an ethernet interface) network interface receives a request. The kernel understands that the request is directed to the Docker subnet, redirects it to the Docker network interface (`docker0`), which, in its turn, is a subnet that interfaces the container's private IP, proxying the request to the appropriate destination IP and Port.

So I tried to isolate the problem: the problem must be something related to how the Kernel is accessing the data and redirecting it to the docker virtual network interface, right? 
- Maybe. Maybe VPN changed the IP routing table, but when I run `ip route show` with VPN enabled and disabled, the only difference is that in the first output the VPN network interface is present.
- Maybe the VPN added firewall rules? I checked `iptables`, but nothing seemed wrong.
- I went back to my first assumption regarding the IP routing tables, but this time i checked with `route -n`. Route manipulates the kernel's IP routing tables. 

And there it was. The VPN added a new IP to the table: its own. And when I decided to check if anything had changed in `resolv.conf`, I found out that the VPN changed the namespace to the same subnet of `route - n` VPN's destination subnet.

Let's check it out:


```
sudo route -n
10.64.0.1       0.0.0.0         255.255.255.255 UH    0      0        0 wg0-vpn


cat /etc/resolv.conf
nameserver 10.64.0.1
```

So, what happened? This is how Karl Matthias[^1] explain an inbound request to Docker's subnet:

> If we have a client somewhere on the network that wants to talk to the nginx server running on TCP port 80 inside Container 1, the request will come into the eth0 interface on the Docker server. Because Docker knows this is a public port, it has spun up an instance of docker-proxy to listen on port 10520. So uor request is passed to the docker-proxy process, which then makes the request to the correct container address and port on the private network. Return traffic from the request flows through the same route. (...) `docker0` is where all the traffic from the Docker containers is picked up to be routed outside the virtual network. 

Docker sets up its own bridge network (`docker0`), and the kernel can route traffic to docker containers directly because it *uses the local network interface*. When VPN changed the DNS server in `resolv.conf` to the VPN network interface, it redirected the traffic through the VPN tunnel. Because of this, the Kernel couldn't route the traffic to the Docker subnet, and the connection failed. The VPN network interface is a virtual network interface, just like the Docker network interface. The difference is that the VPN network interface is a point of interconnection between the computer and the VPN server, while the Docker network interface is a point of interconnection between the computer and the Docker containers.

One final question to ask: if the kernel has access to multiple network interfaces, how does it decide which one to use? There are matching rules, and, one of them is the longest prefix match. The kernel will choose the route with the longest prefix that matches the destination IP address. So if `docker0`'s ip is `172.17.0.0` and the destination address I'm trying to access is `172.17.0.2`, the kernel will route the traffic to `docker0` network interface.

[^1]: Matthias, Karl. Docker: Up & Running: Shipping Reliable Containers in Production. O'Reilly Media, 2015.
