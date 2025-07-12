+++
date = 2024-12-27
title = "How do we talk to the Kernel about namespaces?"
regular = true
+++

In the current Linux kernel, we have three interfaces for namespaces: `clone`, `unshare` and `setns`. 

`clone` is the grandfather of namespace operations[^4]. It's a syscall that creates a new process, similar to `fork`, but with superpowers. When creating a new process with `clone`, you can specify which namespaces[^5] you want the child process to inherit from its parent and which ones should be created anew. For example, if you want a process to have its own PID namespace but share everything else with its parent, you'd use `clone` with the `CLONE_NEWPID` flag. This is actually what happens under the hood when you run a container.[^6]

`setns` is like a passport control for processes - it lets a process enter an existing namespace. Unlike `clone`, which creates new namespaces, `setns` allows a process to join namespaces that already exist. This is super useful when you want a process to "enter" a container that's already running. In fact, this is exactly what happens when you run `docker exec` - the new process uses `setns` to join the namespaces of an existing container.

Here's a cool example: when you start a debugging session in a container, the debugger process needs to see exactly what the container sees. This is where `setns` comes in - it allows the debugger to join all the container's namespaces, making it feel like it's running inside the container itself.

`unshare` is the last piece of the API. The fun part of `unshare` is that we can manipulate with within the shell. Let's explore a little bit more about namespaces by playing around with `unshare`:


```
root@frn:~# unshare --pid --mount-proc --fork /bin/bash
root@frn:~# ps aux
USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
root           1  0.0  0.0   7196  3928 pts/1    S    00:31   0:00 /bin/bash
root           2  0.0  0.0  11084  4388 pts/1    R+   00:31   0:00 ps aux
```

With this command, we are doing the follow: we create a child process with `--fork`, and this child process has two namespaces: `pid` and `proc`. This means that the `/proc` virtual file system, in the perspective of this process, is new, untainted. And its vision on processes IDs is also clean (begins at 1).

In two different shells, if we check the namespace ids for both the parent and the child processes, we can see what's happening. For this exercise, I will display only 4 namespaces: `mnt`, `net`, `pid` and `pid_for_children`. Remember that we passed the mount (`--mount-proc`) and pid flags to unshare:


```
# sudo ls l /proc/pid/ns

# Parent process
lrwxrwxrwx 1 root root 0 Dec 28 00:37 mnt -> 'mnt:[4026532895]' #
lrwxrwxrwx 1 root root 0 Dec 28 00:37 net -> 'net:[4026531840]' 
lrwxrwxrwx 1 root root 0 Dec 28 00:37 pid -> 'pid:[4026532897]' # 
lrwxrwxrwx 1 root root 0 Dec 28 00:37 pid_for_children -> 'pid:[4026532897]' #

# Child process
lrwxrwxrwx 1 frns frns 0 Dec 28 00:37 mnt -> 'mnt:[4026531841]' # 
lrwxrwxrwx 1 frns frns 0 Dec 28 00:37 net -> 'net:[4026531840]'
lrwxrwxrwx 1 frns frns 0 Dec 28 00:37 pid -> 'pid:[4026531836]' # 
lrwxrwxrwx 1 frns frns 0 Dec 28 00:37 pid_for_children -> 'pid:[4026531836]' #
```

We can see that the only namespace that has the same ID between parent and child is the `net` namespace. This is cool, huh? The only thing they share is the network namespace. This isolation is particularly powerful for containerization. When a container runs in its own network namespace, it can have its own IP address, routing tables, and network configuration without interfering with the host system or other containers. This means you can run multiple web servers on port 80 in different containers without conflict, or create complex networking setups where containers communicate through their own virtual networks.

### Let's run a server on a net namespace to see what happens

This feels kind of magic so I want to try this out in a practical way. First, let's create a new network namespace with `ip netns`. 

```
root@frn:~# ip netns add fakens
root@frn:~# ip netns exec fakens bash
```
We are now within the process with a namespaced network. Let's find out our net interfaces:

```
root@frn:~# ip link show
1: lo: <LOOPBACK> mtu 65536 qdisc noop state DOWN mode DEFAULT group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
```

Only the loopback is available. Let's fire up a server:

```
root@frn:~# ip link set lo up
root@frn:~# nc -l 80

```

Now, on the host, let's try to netcat port 80:

```
➜  ~ nc localhost 80
localhost [127.0.0.1] 80 (http) : Connection refused
```

The connection is refused because host's and namespace's networks are completely separated. This means that each has its own protocol stack, including routing tables, iptables, and socket listing. So net namespace not only limited what network interfaces a process could see, but it also created a new network stack for the namespaced process. 

I'm really impressed by this. This example is really interesting, because we can actually test against it. In contrast, creating a namespace with `unshare --pid` is almost dull; we can see that the process tree is not accessible by the child process, but so what? It doesn't mean that behind the scenes there is isolation. With this experiment on net namespaces, though, it became clear what really happens: the process is almost secluded by its own namespaces.


[expensive]: https://www.linuxjournal.com/article/3458
[jails]: https://docs.freebsd.org/en/books/handbook/jails/
[Linux-VServer]: https://en.wikipedia.org/wiki/Linux-VServer
[Zones]: https://docs.oracle.com/en/operating-systems/solaris/oracle-solaris/11.4/use-zones/dev-and-devices-namespace.html
[template-based]: https://docs.openvz.org/openvz_users_guide.webhelp/_templates.html"
[Process Containers]: https://lwn.net/Articles/236480/

[cgroups]: https://lwn.net/Articles/604609/
[namespaces]: https://lwn.net/Articles/766124/

[^1]: https://www.redhat.com/en/blog/history-containers
[^4]: From The Linux Programming Interface: Like fork() and vfork(), the Linux-specific clone() system call creates a new process. It differs from the other two calls in allowing finer control over the steps that occur during process creation. 
[^5]: https://man7.org/linux/man-pages/man2/clone.2.html (Check out the flag masks.)
[^6]: When working with PID namespaces using `clone` in languages like C or Go, there's an important detail to consider: you need to manually mount a new `/proc` file system inside the new namespace. This is because the PID namespace creates a new process numbering system (starting from PID 1), but the original `/proc` still shows PIDs from the parent namespace. Without mounting a new `/proc`, tools like `ps` would show incorrect information. This is why container runtimes always ensure a fresh `/proc` mount when creating new PID namespaces. The mount typically looks something like `mount("proc", "/proc", "proc", MS_NOSUID|MS_NODEV|MS_NOEXEC, NULL)`.

