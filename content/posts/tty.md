+++
date = 2024-04-26
title = "A terminal keyboard"
labels = ["draft"]
+++

<figure class="post-figure-side">
  <img src="/static/tty/dec.png" alt="A DEC-style Televideo terminal keyboard">
</figure>

I'm getting old, so I gifted myself a terminal keyboard. Last years I read this [article](https://www.linusakesson.net/programming/tty/) and got really fascinated by this. Well, I found this DEC-style Televideo terminal keyboard from the 70s or 80s (not sure the exact date).

These old terminal keyboards were sold alongside a "computer terminal." A computer terminal was essentially a "dumb" display and input device. The real computing power was in the mainframe, which was typically placed in another room in the office building. The terminal would send characters to the mainframe and then display the results back to the user. It didn't have its own operating system. The notion of keycodes, scancodes, and other abstractions that we have nowadays didn't exist in the same way.

This is what happened when you used a terminal keyboard: when you pressed a key, let's say "A", the keyboard generated a specific electrical signal. The terminal would interpret this signal, convert it to ASCII or another character encoding, and transmit it to the mainframe using a protocol like RS-232. The mainframe would process this input according to whatever program was running, and send results back to the terminal for display.

Something like:

[KEYBOARD/TERMINAL] <--wire--> [MAINFRAME]

ASCII ASCII

(01000001) "This is 'A'"

Modern keyboards don't work like this. They don't mess with bytes and ASCII directly. Instead, they just send a [scancode](https://en.wikipedia.org/wiki/Scancode), which is basically just a code saying which key you pressed. Your computer's OS figures out what to do with it using the USB HID protocol, which is pretty complex but gives us all those nice features like different layouts and function keys.

Another cool thing about these old terminal keyboards is how wildly different their connections were. It wasn't like today where everything is just USB. Every company was doing their own thing with serial connections back then.

Computer terminals had differences between themselves, both from physical and encoding perspectives.

DEC had their weird modified RS-232 with custom connectors. IBM did their own proprietary stuff. Wyse, Televideo, and others all had their own setups. Even when they used the same-looking connectors like DB-25 or DB-9, they'd wire them up differently just to keep things interesting.

The way they encoded text could vary too:

- Regular [7-bit ASCII](https://www.ascii-code.com/ASCII) (128 characters)
- Various [8-bit extended ASCII versions](https://en.wikipedia.org/wiki/Extended_ASCII) (IBM had CP437, DEC had their Multinational thing)
- IBM even made their own system called [EBCDIC](https://en.wikipedia.org/wiki/EBCDIC).

That's why some companies like Televideo started making keyboards that could switch between different modes. They put some DIP switches on them that you could flip and pretend to be different terminals.

One thing that I truly find fascinating is how modern terminals inherited from those old computer terminals.

When you open Terminal on a Mac or Linux, you're using a terminal emulator (tmux, wezterm, etc), software pretending to be those old physical terminals. The "Terminal" part of the name isn't there without reason, it's literally emulating what those [DEC VT100s](https://en.wikipedia.org/wiki/VT100) and Televideo terminals used to do in hardware.

For example, take the TERM environment variable - it often defaults to "xterm" or something like "xterm-256color." That "xterm" refers to the X Window System Terminal, which itself was emulating capabilities of hardware terminals (I guess?). 

We have a bunch of legacy things in our own setups. Example, my `TERM` environment variable is `xterm-256color` (cool discussion about this [here](https://stackoverflow.com/questions/10003136/what-is-the-difference-between-xterm-color-xterm-256color)).

Classic terminals were often limited to [80 columns](https://softwareengineering.stackexchange.com/questions/148677/why-is-80-characters-the-standard-limit-for-code-width) by 24 or 25 rows, and many modern terminal defaults still reflect this. It's why terminal text still wraps at 80 characters in many configurations. (Check out how's yours configured: `stty size`)

Anyways, the modern notion of a "terminal" still has ties to the old computer terminals, which is interesting as hell. 

This keyboard came with Hi-Tek "space invaders" switch, which I frankly love. I've used Topre keyboards (especially Realforce 87u and HHKBs) for the last ten years, then I switched to custom kmechanical keyboards. Space invaders switches feel really nice and, honestly, I like them better than Topre switches or mechanical ones.
