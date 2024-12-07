+++
date = 2024-08-08
title = "What happens when you call print()?: tty, buffering, etc."
+++ 

A few months back I encountered an interesting behavior while debugging a legacy Flask API running on Docker: since I had no time to setup a proper debugger, I began to add print statements to the backend code (don't judge me, I bet you are lazy too). The problem was: the print output was inconsistent: I tried to reload the React frontend once, and nothing appeared. Then I reload again. Nothing. A few more times, and suddenly the text was output in a single block.

What happened? Let's find out how `print` works, and what's line and block buffering.

**how print() works**

Python `print()` actually calls `sys.stdout.write()`. Let's check out how this works:


```
import sys
def hello():
    print("hello from print")
    sys.stdout.write("hello from stdout.write")

hello()
```

In `strace`, we can spot two `write` calls: 

```
write(1, "hello from print\n", 17hello from print
)      = 17
write(1, "hello from stdout.write", 23hello from stdout.write) = 23
```

Python's `print` actually calls `sys.stdout.write` internally and appends a `\n` by default. This does not happen by chance or arbitrarily. The new line is used to *flush* its contents to the file (be it a real file on disk, be it a terminal (`tty`)). In C we see the same behavior regarding to `flush`, but we need to add the new line manually. This is not a Python specific behavior.

Let's see what Python's documentation says about the `print` function all:

```
 print(*objects, sep=' ', end='\n', file=None, flush=False)

The file argument must be an object with a write(string) method; if it is not present or None, sys.stdout will be used.
```

Adding a new line is a detail the system expects. Its origins probably have some relation to the way we used to type in old typing machines. In any case, the operating system uses new lines to handle *line buffering*; this reverberates on Python: whenever Python sees a new line, it flushes the content of the buffer to display the text on stdout.

Python doesn't always use line buffering, though (more on this below). If we pipe the output (or redirect it) of this program to cat, for example, Python will change to block buffering, outputting the print contents only when the buffer is full. (I think the size of the buffer is 8KB?). We can check this out with something like this:

```
import time

while True:
    print("hello from print")
    time.sleep(.01)
```

If you `python file.py | cat`, you won't see "hello from print" being written to stdout. You will only see the block of text once the buffer is full, so it will output everything at once.

 **A few words on write()**
 
`strace` showed us that the operating system calls `write(fd, ...)` when Python prints something. But what's really happening? I found a really great answer in the [Linux Programming Interface](https://man7.org/tlpi/): `write()` doesn't directly access the physical file or terminal (such as stdout). Instead, it transfers data from a user-space buffer to a kernel buffer cache.

For disk files, the operating system may defer writing to the physical storage device for performance reasons. The data is eventually flushed to the file either by the kernel (when the buffer fills up) or explicitly by the program (via `fflush`, for example).

If a process issues a `read()` for data that has been written but not yet flushed to disk, the operating system will supply the data from the buffer cache rather than the physical file. For terminals (e.g., stdout), `write()` may bypass this deferred behavior, depending on whether the stream is line-buffered or unbuffered.

The pass-through-buffers behavior is an important mechanism to reduce system calls (the `flush` occurs only when certain conditions are satisfied; but image what would happen if this was not the case).

**buffering modes?**

Line, blocking and non-blocking buffering is not something that is specific to Python. It's in the C standard library. `setvbuf` is called behind the scenes whenever an I/O function from libc is called; the OS handles the buffering and we are free to not care much about this. From manpage:

> The three types of buffering available are unbuffered, block buffered, and line buffered.  When an output stream is unbuffered, information appears on the destination file or terminal as soon as written; when it is block buffered, many characters are saved up and written as a block; when it is line buffered, characters are saved up until a newline is output or input is read from any stream attached to a terminal device (typically stdin). (...) 

> Normally all files are block buffered. If a stream refers to a terminal (as stdout normally does), it is line buffered. (...) The setvbuf() function may be used on any open stream to change its buffer. 

**why didn’t Docker write to a `tty`?**

One thing I did not understand at first was why Docker wasn't writing to stdout. I was calling `print()`, right? I was executing the process. Everything was cool. I found out that the inconsistency happened because Python determines its buffering mode based on whether the output file descriptor is connected to a terminal, as detected by `isatty()`[^1] (tty stands for `teletypewriter`. A legacy name that persisted from the days when we used these machines for telecommunication). 

In a Docker container, unless the -t flag is used, the standard output is not connected to a terminal but instead to a pipe or a file-like object. This causes `isatty()` to return false, and Python switches from line buffering to block buffering.

When a Python program runs, its standard output is typically attached to a file descriptor, which could point to a terminal, a file, or a pipe. The behavior of `isatty()` is central here:

- If `isatty()` returns true (indicating the file descriptor is a terminal), Python defaults to line buffering. Each line (ending with \n) triggers an immediate flush to stdout.
- If `isatty()` returns false (e.g., for pipes or files), Python uses block buffering, where data accumulates in an internal buffer (usually 4KB or 8KB) before being flushed.

Without the [-t](https://docs.docker.com/reference/cli/docker/container/run/#tty) flag, Docker does not attach a pseudo-terminal to the container’s stdout, so `isatty()` fails. Consequently, Python treats stdout as a pipe, enabling block buffering.

Docker has a pseudo-TTY[^2], When you pass the -t flag to Docker, it creates a pseudo-TTY and attaches it to the container's stdin and stdout. Internally, this makes `isatty()` return true, as the file descriptor is now associated with a terminal-like device. The pseudo-TTY essentially simulates a real terminal, altering how the Python runtime configures stdout.

[^1]: https://www.man7.org/linux/man-pages/man3/isatty.3.html
[^2]: I was searching for more information and found [this](https://stackoverflow.com/questions/30137135/confused-about-docker-t-option-to-allocate-a-pseudo-tty) to be a good explanation.

