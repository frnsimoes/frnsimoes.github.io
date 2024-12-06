+++
date = 2024-08-08
title = "strace print"
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

**why does it happen?**

Internally, Python chooses the buffering mode based on `isatty()`[^1]. This function tests if the file descriptor is trying to write to the terminal (tty stands for `teletypewriter`. A legacy name that persisted from the days when we used these machines for telecommunication).

If `isatty` returns `true`, then Python buffering is line buffering; if `false`, it's block buffering. 

**docker wasn't writing to a `tty`?**

I wasn't running Docker with the [-t](https://docs.docker.com/reference/cli/docker/container/run/#tty) flag. By using `-t`, Docker attaches a pseudo-tty to the container, satisfying the `isatty()` requirement. Another thing I could have done is change the env [PYTHONUNBUFFERED](https://docs.python.org/3/using/cmdline.html#cmdoption-u) to a non-empty string value. This would force the stdout to be unbuffered (no line or block buffering).


[^1]: https://www.man7.org/linux/man-pages/man3/isatty.3.html
