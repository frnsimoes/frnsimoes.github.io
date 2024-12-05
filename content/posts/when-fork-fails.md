+++
date = 2024-10-22
title = "Forcing fork() to fail"
tags = ["OS theory and fun"]
+++

What if `fork()` fails?[^1] Well, this is really a problematic issue since you have to handle the return value manually. `fork()` has three possible return values: If it's `0`, we know we are in the child's realm. If it's a positive integer, this represents the child's `pid`, and if it's `-1`, `fork()` has failed. 

But what happens when: you forget to test `pid` equals `-1` and you want to send a sigkill to the child's `pid` in the parent's process? I was reading [rachelbythebay] post on this problem and thought: how could I make `fork()` fail? Maybe by allocating lots of memory to the process. Perhaps by using `ulimit(3)` to limit the allowed processes? But these felt kind of troublesome, so I found `getrlimit`, a system call that limits a resource[^2] for the user.

Combined with `RLIMIT_NPROC`[^3], `getrlimit` can set the maximum number of processes allowed for my user to `1` (I know, dumb and dangerous), forcing `fork()` to fail.

```
int main() {
    struct rlimit rl;
    
    getrlimit(RLIMIT_NPROC, &rl);
    
    rl.rlim_cur = 1;
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

In a non-buggy execution, the parent would create a child with `fork()`, the child would do it's job while the parent's gently wait for it to finish, then the parent would do something, and the execution would be finished (or [die], depending on your mood). However, in this case, what's happening is: we forgot to check if `fork()` failed, and we are sending a `SIGKILL` (`9`) to the child's `pid`, which is `-1`, resulting a the termination of all processes in the process group. Think about the potential damage this could cause in a real-world scenario.

[^1]: If you don´t think it can happen, a quick search on the internet will show you otherwise. [KDE] had this problem a while ago. Also, I found this heart-tugging story on HN:

    > When I was young and really didn't understand Unix, my friend and were summer students at NBS (now NIST), and one fine afternoon we wondered what would happen if you ran fork() forever.

    > We didn't know, so we wrote the program and ran it.
    
    > This was on a PDP-11/45 running v6 or v7 Unix. The printing console (some DECWriter 133 something or other) started burping and spewing stuff about fork failing and other bad things, and a minute or two later one of the folks who had 'root' ran into the machine room with a panic-stricken look because the system had mostly just locked up.
    
    > "What were you DOING?" he asked / yelled.
    
    > "Uh, recursive forks, to see what would happen."
    
    > He grumbled. Only a late 70s hacker with a Unix-class beard can grumble like that, the classic Unix paternal geek attitude of "I'm happy you're using this and learning, but I wish you were smarter about things."
    
    > I think we had to hard-reset the system, and it came back with an inconsistent file system which he had to repair by hand with ncheck and icheck, because this was before the days of fsck and that's what real programmers did with slightly corrupted Unix file systems back then. Uphill both ways, in the snow, on a breakfast of gravel and no documentation.
    
    > Total downtime, maybe half an hour. We were told nicely not to do that again. I think I was handed one of the illicit copies of Lions Notes a few days later. "Read that," and that's how my introduction to the guts of operating systems began.

    Thanks, kabdib.
    
[^2]: From the man page: The getrlimit() and setrlimit() system calls get and set resource limits.  Each resource has an associated soft and hard limit, as defined by the rlimit structure


[^3]: RLIMIT_NPROC
              This is a limit on the number of extant process (or, more precisely on Linux, threads) for the real user ID of the calling process.  So long as the current number of processes belonging to this process's real user ID is greater than or  equal  to  this
              limit, fork(2) fails with the error EAGAIN.



[rachelbythebay]: https://rachelbythebay.com/w/2014/08/19/fork/
[die]: https://youtube.com/clip/UgkxuEH56Jf9LhkN-6BP6K-b1hm4xoOxmHuT
[KDE]: https://www.mail-archive.com/kde-bugs-dist@kde.org/msg811832.html

