+++
date = 2024-09-22
title = "Forcing fork() to fail"
tags = ["OS theory and fun"]
+++

What if `fork()` fails? Well, this is really a problematic issue since you have to handle the return value manually. `fork()` has three possible return values: If it's `0`, we know we are in the child's realm. If it's a positive integer, this represents the child's `pid`, and if it's `-1`, `fork()` has failed.

But what happens when: you forget to test pid equals -1 and you want to send a sigkill to the child's PID in the parent's process? I was reading [rachelbythebay] post on this problem and thought: how could I make `fork()` fail? Maybe by allocating lots of memory to the process. Perhaps by using `ulimit(3)` to limit the allowed processes? But these felt kind of troublesome (and `ulimit` is deprecated), so I found `getrlimit`, a system call that limits a resource[^1] for the user.

Combined with `RLIMIT_NPROC`[^2], `getrlimit` can set the maximum number of processes allowed for my user to `0` (I know, dumb and dangerous), forcing `fork()` to fail.

```
#include <stdio.h>
#include <sys/resource.h>
#include <unistd.h>
#include <signal.h>
#include <wait.h>

int main() {
    struct rlimit rl;
    
    getrlimit(RLIMIT_NPROC, &rl);
    
    rl.rlim_cur = 0;
    setrlimit(RLIMIT_NPROC, &rl);

    pid_t pid = fork();

    if (pid == 0) {
        printf("Child\n");
    } else {
        // If you wait, no need to send a sigkill
        kill(pid, SIGKILL);
        printf("Parent\n");

    return 0;
}
```

Thankfully, this would only affect processes created by the same user running the program. Let's us all hope that good programmers know how to handle `fork()` failures.

[^1]: From the man page: The getrlimit() and setrlimit() system calls get and set resource limits.  Each resource has an associated soft and hard limit, as defined by the rlimit structure


[^2]: RLIMIT_NPROC
              This is a limit on the number of extant process (or, more precisely on Linux, threads) for the real user ID of the calling process.  So long as the current number of processes belonging to this process's real user ID is greater than or  equal  to  this
              limit, fork(2) fails with the error EAGAIN.


[rachelbythebay]: https://rachelbythebay.com/w/2014/08/19/fork/
