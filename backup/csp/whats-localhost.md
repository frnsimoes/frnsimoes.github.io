+++
date = 2024-03-20
title = "What is the loopback?"
csp = true
+++

Besides being a hostname, the underlaying mechanism of localhost is to be a loopback interface. It's kinda of a local virtual network interface. Sending something to localhost is very similar to sending something out of the physical network but instead it reflects back from inside of the OS's TCP/IP, the network stack. 

A message that is addressed to localhost goes into the network stack of the OS, follows most of the same code paths, and rather than going to a network card, it's ultimately reflected back as if it had arrived from the outside network, and mimics.
