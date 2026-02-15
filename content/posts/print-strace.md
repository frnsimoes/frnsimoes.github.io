+++
date = 2024-05-20
title = "Line buffering, tty and write(2)"
description = "Understanding linux line buffering"
+++ 

A few months back I encountered an interesting behavior while debugging a legacy Flask API running on Docker: since I had no time to setup a proper debugger, I began to add print statements to the backend code (don't judge me, I bet you are lazy too). The problem was: the print output was inconsistent: I tried to reload the React frontend once, and nothing appeared. Then I reload again. Nothing. A few more times, and suddenly the text was output in a single block.


Why is that? First we need to understand what `print` is doing behind the scenes, and get a notion to the buffering from the operating system perspective.

### How does print work?

```
import sys

def hello():
    print("hello from print")

hello()
```

Let me run this program with `strace` so we can get insights by checking out the syscalls:

```
write(1, "hello from print\n", 17hello from print
)      = 1
```

We can see that print called `write(2)`. The first argument, 1, is the stdout; The second one is what we want to print to stdout, and the third is the size. We can also see that print appended a new line (`\n`) by default.

With the information we have right now, there are two questions that requires our attention: 1. Why does print appended a new line? 2. How `write(2)` works?

### The historical context of \n and why print uses it

We actually had physical terminals in the early days of computing, and even before. For example, stock tickers were 'electro-mechanical machines consisting of a typewriter, a long pair of wires, and a ticker tape printer, designed to distribute stock prices over long distances in real time'[^1]. Later, the Telex network[^2] was developed, enabling the transmission of messages via teleprinters over telephone lines.

Teletypes were *devices*, external physical tools, with a keyboard, wires, and screen, used to write something to be send to another location. They got extinct, but the "teletype as a device" didn't. 

But how does the teletype's keyboard sends words to the teletype screen? Imagine a phrase is being typed: "hello from new york city"; at what moment should the teletype send the message? How does it know it is complete? The terminal has two modes: *cooked* (!!!) mode and *raw* mode. What's the difference? Raw mode works like this:

- Input is delivered to the application immediately, without waiting for a new line (`\n`, remember?).
- Special characters (such as backspace) are not pre-processed (so if the user typed AB<BACKSPACE>C, raw mode interprets it as is).
- Line editing features are disabled.

### Buffering modes?

New lines, as we saw, are used as delimiters to signal that the message is ready to be consumed. This subtle pratice from the early days arrived to our days translated by the notion of *buffering modes*. 

We have three main buffering modes: line, blocking and non-blocking. This is not a Python specific feature. It's in the C standard library. The system call `setvbuf` is called behind the scenes whenever an I/O function (including `write(2)`) from libc is called; the OS handles the buffering and we are free to not care much about this. From manpage:

Line, blocking and non-blocking buffering is not something that is specific to Python. It's in the C standard library. `setvbuf` is called behind the scenes whenever an I/O function from libc is called; the OS handles the buffering and we are free to not care much about this. From manpage:

> The three types of buffering available are unbuffered, block buffered, and line buffered.  When an output stream is unbuffered, information appears on the destination file or terminal as soon as written; when it is block buffered, many characters are saved up and written as a block; when it is line buffered, characters are saved up until a newline is output or input is read from any stream attached to a terminal device (typically stdin). (...) 

> Normally all files are block buffered. If a stream refers to a terminal (as stdout normally does), it is line buffered. (...) The setvbuf() function may be used on any open stream to change its buffer. 

But Python doesn't always use line buffering. If we pipe the output (or redirect it) of this program to cat, for example, Python will change to block buffering, outputting the print contents only when the buffer is full. (I think the size of the buffer is 8KB?). We can check this out with something like this:

```
import time

while True:
    print("hello from print")
    time.sleep(.01)
```

If you `python file.py | cat`, you won't see "hello from print" being written to stdout. You will only see the block of text once the buffer is full, so it will output everything at once.

### Ok, how does write(2) work?

`strace` showed us that the operating system calls `write(fd, ...)` when Python prints something. But what's really happening? I found a really great answer in the [Linux Programming Interface](https://man7.org/tlpi/): `write(2)` doesn't directly access the physical file or terminal (such as stdout). Instead, it transfers data from a user-space buffer to a kernel buffer cache.

For disk files, the operating system may defer writing to the physical storage device for performance reasons. The data is eventually flushed to the file either by the kernel (when the buffer fills up) or explicitly by the program (via `fflush`, for example).

If a process issues a `read()` for data that has been written but not yet flushed to disk, the operating system will supply the data from the buffer cache rather than the physical file. For terminals, `write()` may bypass this deferred behavior, depending on whether the stream is line-buffered or unbuffered.

The pass-through-buffers behavior is an important mechanism to reduce system calls (the `flush` occurs only when certain conditions are satisfied; but image what would happen if this was not the case).


### Alright, but why didn't print write to docker stdout?


One thing I did not understand at first was why Docker wasn't writing to stdout. I was calling `print()`, right? I was executing the process. Everything was cool. I found out that the inconsistency happened because Python determines its buffering mode based on whether the output file descriptor is connected to a terminal, as detected by `isatty()`[^3]. 

In a Docker container, unless the -t flag is used, the standard output is not connected to a terminal but instead to a pipe or a file-like object. This causes `isatty()` to return false, and Python switches from line buffering to block buffering.

When a Python program runs, its standard output is typically attached to a file descriptor, which could point to a terminal, a file, or a pipe. The behavior of `isatty()` is central here:

- If `isatty()` returns true (indicating the file descriptor is a terminal), Python defaults to line buffering. Each line (ending with \n) triggers an immediate flush to stdout.
- If `isatty()` returns false (e.g., for pipes or files), Python uses block buffering, where data accumulates in an internal buffer (usually 4KB or 8KB) before being flushed.

Without the [-t](https://docs.docker.com/reference/cli/docker/container/run/#tty) flag, Docker does not attach a pseudo-terminal to the container’s stdout, so `isatty()` fails. Consequently, Python treats stdout as a pipe, enabling block buffering.

Docker has a pseudo-TTY[^4], When you pass the -t flag to Docker, it creates a pseudo-TTY and attaches it to the container's stdin and stdout. Internally, this makes `isatty()` return true, as the file descriptor is now associated with a terminal-like device. The pseudo-TTY essentially simulates a real terminal, altering how the Python runtime configures stdout.
 
[^1]: https://www.linusakesson.net/programming/tty/
[^2]: https://en.wikipedia.org/wiki/Telex
[^3]: https://www.man7.org/linux/man-pages/man3/isatty.3.html
[^4]: I was searching for more information and found [this](https://stackoverflow.com/questions/30137135/confused-about-docker-t-option-to-allocate-a-pseudo-tty) to be a good explanation.



