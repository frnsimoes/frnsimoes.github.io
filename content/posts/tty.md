+++
date = 2025-04-26
title = "I bought a DEC-style terminal keyboard"
labels = ["post"]
subjects = ["history"]
+++

![alt](/static/tty/dec.png)

My birthday is next month, so I bought myself something I'd wanted for a while: a terminal keyboard. Last year I read this [article](https://www.linusakesson.net/programming/tty/) about the history of the terminal and it fascinated me. I found a DEC-style Televideo terminal keyboard from the 70s or 80s (I can't be sure of the exact date) and took advantage of the opportunity to learn a few things.

These old terminal keyboards were sold alongside a "computer terminal," which was essentially a dumb display and input device. The real computing power lived in the mainframe, typically in another room of the office building. The terminal would send characters to the mainframe and display the results back to the user - it didn't have its own operating system, and the notion of keycodes, scancodes, and other abstractions that we have nowadays didn't exist in the same way.

When you pressed a key, let's say "A", the keyboard generated a specific electrical signal. The terminal would interpret this signal, convert it to ASCII or another character encoding, and transmit it to the mainframe using a protocol like RS-232. The mainframe would process the input according to whatever program was running and send results back to the terminal for display.

```
[KEYBOARD/TERMINAL] <--wire--> [MAINFRAME]
        ASCII                       ASCII
     (01000001)                 "This is 'A'"
```

![alt](/static/tty/term-diagram.png)

Modern keyboards don't work like this - they don't deal with bytes and ASCII directly. Instead they send a [scancode](https://en.wikipedia.org/wiki/Scancode), which is just a code identifying which key was pressed, and your computer's OS figures out what to do with it using the USB HID protocol.

Another thing about these old keyboards is how wildly different their connections were. It wasn't like today where everything is USB - every company was doing their own thing with serial connections. DEC had their modified RS-232 with custom connectors, IBM did their own proprietary stuff, and Wyse, Televideo, and others all had their own setups. Even when they used the same-looking connectors like DB-25 or DB-9, they'd wire them up differently.

The way they encoded text varied too: regular [7-bit ASCII](https://www.ascii-code.com/ASCII) with 128 characters, various [8-bit extended ASCII versions](https://en.wikipedia.org/wiki/Extended_ASCII) (IBM had CP437, DEC had their Multinational character set), and IBM even made their own entirely separate system called [EBCDIC](https://en.wikipedia.org/wiki/EBCDIC). That's why companies like Televideo started making keyboards with DIP switches you could flip to emulate different terminals.

What I find fascinating is how modern terminals inherited from all of this. When you open a terminal on Mac or Linux, you're using a terminal emulator - software pretending to be those old physical terminals. The "Terminal" part of the name isn't there without reason, it's literally emulating what [DEC VT100s](https://en.wikipedia.org/wiki/VT100) and Televideo terminals used to do in hardware.

The legacy shows up everywhere once you know what to look for. The TERM environment variable often defaults to "xterm" or "xterm-256color," where "xterm" refers to the X Window System Terminal, which itself was emulating the capabilities of hardware terminals - the terminal emulating the emulator. Classic terminals were limited to [80 columns](https://softwareengineering.stackexchange.com/questions/148677/why-is-80-characters-the-standard-limit-for-code-width) by 24 or 25 rows, and many modern terminal defaults still reflect this. It's why text still wraps at 80 characters in many configurations.

And then there's `tty` and `isatty()` - programs use these to check if their input/output is connected to a "real terminal" instead of a pipe or a file. The modern notion of a terminal still has ties to the old computer terminals, and we carry all of it around without even noticing.
