+++
date = 2024-08-08
title = "A block buffering problem"
tags = ["OS theory and fun"]
+++ 

A few months back I encountered an interesting behavior: I was trying to debug a legacy Flask API running on Docker. Since I had no time to setup a proper debugger, I began to add print statements to the backend code (don't judge me, I bet you are lazy too). The problem was: the print output was inconsistent: I tried to reload the React frontend once, and nothing appeared. Then I reload again. Nothing. A few more times, and suddenly the text was output in a single block.

What happened? Let's find out how `print` works, and what's line and block buffering.

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

The difference between them is that `print` adds a new line; `sys.stdout.write` doesn't. Why?

Python's `print` actually calls `sys.stdout.write` internally and adds a `\n`. This happens because Python is line buffering `print()`. So whenever Python sees a new line, it flushes the content of the buffer to display the text on stdout.

Python doesn't always use line buffering, though. If we pipe the output (or redirect it) of this program to cat, for example, Python will change to block buffering, outputting the print contents only when the buffer is full. (I think the size of the buffer is 8KB?). We can check this out with something like this:

```
import time

while True:
    print("hello from print")
    time.sleep(.01)
```

If you `python file.py | cat`, you won't see "hello from print" being written to stdout. You will only see the block of text once the buffer is full, so it will output everything at once.

**how linux `write()` behaves?**

**why didn’t Docker write to a `tty`?**

One thing I did not understand at first was why Docker wasn't writing to `stdout`. I had print() logs, right? I was executing the process. Everything was cool. I found out that the inconsistency happened because Python determines its buffering mode based on whether the output file descriptor is connected to a terminal, as detected by `isatty()`[^1] (tty stands for `teletypewriter`. A legacy name that persisted from the days when we used these machines for telecommunication). In a Docker container, unless the -t flag is used, the standard output is not connected to a terminal but instead to a pipe or a file-like object. This causes `isatty()` to return false, and Python switches from line buffering to block buffering.

When a Python program runs, its standard output is typically attached to a file descriptor, which could point to a terminal, a file, or a pipe. The behavior of `isatty()` is central here:

- If `isatty()` returns true (indicating the file descriptor is a terminal), Python defaults to line buffering. Each line (ending with \n) triggers an immediate flush to `stdout`.
- If `isatty()` returns false (e.g., for pipes or files), Python uses block buffering, where data accumulates in an internal buffer (usually 4KB or 8KB) before being flushed.

Without the [-t](https://docs.docker.com/reference/cli/docker/container/run/#tty) flag, Docker does not attach a pseudo-terminal to the container’s `stdout`, so `isatty()` fails. Consequently, Python treats `stdout` as a pipe, enabling block buffering.

Docker has a pseudo-TTY[^2], When you pass the -t flag to Docker, it creates a pseudo-TTY and attaches it to the container's stdin and `stdout`. Internally, this makes `isatty()` return true, as the file descriptor is now associated with a terminal-like device. The pseudo-TTY essentially simulates a real terminal, altering how the Python runtime configures `stdout`.

**but what's a tty, really?**
https://unix.stackexchange.com/questions/4126/what-is-the-exact-difference-between-a-terminal-a-shell-a-tty-and-a-con


**a workaround**

If you set [PYTHONUNBUFFERED](https://docs.python.org/3/using/cmdline.html#cmdoption-u) or use the -u flag, Python bypasses the default logic entirely, ignoring `isatty()` and forcing unbuffered output. Internally, this disables the use of a buffer for `stdout` and stderr, ensuring all writes go directly to the underlying file descriptor without delay. While practical, this bypass skips Python’s internal optimization mechanisms, making it a less nuanced solution compared to understanding and controlling the environment directly.

[^1]: https://www.man7.org/linux/man-pages/man3/isatty.3.html
[^2]: this is a nice informative comment on [stackoverflow](https://stackoverflow.com/questions/30137135/confused-about-docker-t-option-to-allocate-a-pseudo-tty):
    The -t option goes to how Unix/Linux handles terminal access. In the past, a terminal was a hardline connection, later a modem based connection. These had physical device drivers (they were real pieces of equipment). Once generalized networks came into use, a pseudo-terminal driver was developed. This is because it creates a separation between understanding what terminal capabilities can be used without the need to write it into your program directly (read man pages on stty, curses). So, with that as background, run a container with no options and by default you have a stdout stream (so docker run | <cmd> works); run with -i, and you get stdin stream added (so <cmd> | docker run -i works); use -t, usually in the combination -it and you have a terminal driver added, which if you are interacting with the process is likely what you want. It basically makes the container start look like a terminal connection session.
