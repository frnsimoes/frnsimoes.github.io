Working with the terminal (and with `stdout` in general) has a lot of tricks. In a past project, I was trying to debug a legacy Flask API running on Docker. Since I had no time to setup a proper debugger, I began to add print statements to the backend code (don't judge me, I bet you would do the same). The problem was: the print output was inconsistent: I tried to reload the React frontend once, and nothing appeared. Then I reload again. Nothing. AA few more times, and suddenly the text started to output repeatedly in the terminal. 

I didn't understand why this happened at the time. I was playing around today and found out that buf


A few months back I encountered an interesting behavior: I was trying to debug a legacy Flask API running on Docker. Since I had no time to setup a proper debugger, I began to add print statements to the backend code (don't judge me, I bet you are lazy too). The problem was: the print output was inconsistent: I tried to reload the React frontend once, and nothing appeared. Then I reload again. Nothing. A few more times, and suddenly the text started to output repeatedly in the terminal. 

Why did this happen?

Here is with what I've been wasting my time this evening:
`

```
import sys
import time
def hello():
    # print('hello p') #1
    # sys.stdout.buffer.write(b'hello b') #2
    # sys.stdout.write('hello nb\n') #3

hello()
``` 

Let's see what happens when I use a redirection output to a file.


```
# 1
➜  frnsimoes.github.io git:(main) ✗ python p.py > t.txt
➜  frnsimoes.github.io git:(main) ✗ ps aux | grep p.py
frns       22691  0.0  0.0   6332  2112 pts/10   S+   02:44   0:00 grep --color=auto --exclude-dir=.bzr --exclude-dir=CVS --exclude-dir=.git --exclude-dir=.hg --exclude-dir=.svn --exclude-dir=.idea --exclude-dir=.tox --exclude-dir=.venv --exclude-dir=venv p.py


➜  frnsimoes.github.io git:(main) ✗ cat t.txt
hello p


# 2

➜  frnsimoes.github.io git:(main) ✗ echo "" > t.txt
➜  frnsimoes.github.io git:(main) ✗ cat t.txt

➜  frnsimoes.github.io git:(main) ✗ python p.py > t.txt
➜  frnsimoes.github.io git:(main) ✗ cat t.txt
hello b%


➜  frnsimoes.github.io git:(main) ✗ ps aux | grep p.py
frns       23703  0.0  0.0  13888  7948 pts/3    Sl+  02:48   0:00 nvim p.py

➜  frnsimoes.github.io git:(main) ✗ sudo cat /proc/23703/stack
[<0>] do_epoll_wait+0x698/0x7d0
[<0>] do_compat_epoll_pwait.part.0+0xb/0x70
[<0>] __x64_sys_epoll_pwait+0x91/0x140
[<0>] do_syscall_64+0x55/0xb0
[<0>] entry_SYSCALL_64_after_hwframe+0x6e/0xd8


# 3
➜  frnsimoes.github.io git:(main) ✗ kill 23703
➜  frnsimoes.github.io git:(main) ✗ echo "" > t.txt
➜  frnsimoes.github.io git:(main) ✗ python p.py > t.txt
➜  frnsimoes.github.io git:(main) ✗ cat t.txt
hello nb
➜  frnsimoes.github.io git:(main) ✗ ps aux | grep p.py
frns       24914  0.0  0.0   6332  2120 pts/10   S+   02:49   0:00 grep --color=auto --exclude-dir=.bzr --exclude-dir=CVS --exclude-dir=.git --exclude-dir=.hg --exclude-dir=.svn --exclude-dir=.idea --exclude-dir=.tox --exclude-dir=.venv --exclude-dir=venv p.py
``` 



