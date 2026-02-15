+++
date = 2024-08-22
title = "Shell internals: builtins and source"
+++

There are many aspects of how the shell works that seem magical to me, particularly when it comes to variables, loading things into memory, forking processes, executing commands, and so on. For example, understanding how the shell manages environment variables and modifies the current session’s state requires understanding concepts like process groups, session ids, and memory space. I will dedicate this lazy sunday afternoon to explore more about the shell.

## Types, builtins

There is a magical `type` in the shell called `builtin`. Some commands are builtin:

```
➜  ~ type cd
cd is a shell builtin
➜  ~ type echo
echo is a shell builtin
```

But some are not:

```
➜  ~ type mkdir
mkdir is /usr/bin/mkdir
```

When a shell runs a command, it essentially can do one of these two things: 1. execute something that is available in its own memory space (hence the builtin); 2. execute something that is external to its memory space (surprise, surprise, hence the need for `exceve`).

Let's try to strace `echo` and see what happens:

```
➜  ~ strace echo hello | head
execve("/usr/bin/echo", ["echo", "hello"], 0x7ffd741cb2d8 /* 36 vars */) = 0
```

What? I'm surprised too. Wasn't `echo` a builtin? Why did it `execve` something `/usr/bin/echo`? Apparently, `strace` forced the shell to call another `echo`, and not the builtin one. Let's try to force the builtin:

```
➜  ~ strace builtin echo hello
strace: Can't stat 'builtin': No such file or directory
➜  ~ builtin echo hello
hello
```

We can't strace the builtin echo because it lives in the same address space as the shell process itself, so it doesn't interact the the system resources, and there are no system calls. From the GNU docs:

> Builtin commands are contained within the shell itself. When the name of a builtin command is used as the first word of a simple command (see Simple Commands), the shell executes the command directly, without invoking another program. Builtin commands are necessary to implement functionality impossible or inconvenient to obtain with separate utilities.

In any case, I'm surprised that there is also the coreutils `echo` command:

```
➜  ~ type /usr/bin/echo
/usr/bin/echo is /usr/bin/echo
```

But we can clearly say that the builtin commands are within the shell process itself, otherwise exporting a variable would be a messy thing, right?

## Shell sessions and process groups

Something that always bugged me was the `source` command. Every time we make a change in .zshrc or .bashrc we source the file to see the new effects. Why? How does it work? Unix uses two types of control over processes: processes group and session ids.

A process group is kind of a collection of related processes. You can signal them all at once.

```
➜ ps -o pid,pgid,comm | grep bash
22851 22851 bash
22852 22851 bash
48233 48233 bash
48234 48233 bash
```

In this example, we have two process groups of bash processes: `22851` and `48233`. Each of them have two processes running. We can also check all processes related to a group (by name) with `pgrep`. A session, on the other hand, is a collection of process groups; sessions are used for job control (signaling, for example). We can get the `sid` a processes is in with the `getsid(2)`.

Each process has an enrivonment list. For example, if you want to know every variable available in the current process, you can check it with `declare -x`.

It is important to note that whenever a process creates a child (by executing `./script`, for example, and calling `clone()`), it may share its environment list with the child. But we can also set environment variables exclusively to a child's proces. This can be achieved by execution, for example, `HELLO='hello' ./script'`

We can also check what are the child processes of a process, if you are interested. Try this: `pstree -aps <PID>`, to see how your the children of `<PID>`. To check the environment list of the process, try `sudo cat /proc/<PID>/environ`. These are cool experiments to know how the environment works.

## Sourcing files

What really happens when we `source` a file? I always had the impression that sourcing a file is telling the terminal to "take this thing that is in this file and load it into your process address space so you can have direct access to it." But is it really the case?

When we source a file (or use the `.` command, which is equivalent), we're telling the shell to read and execute commands from that file in the current shell environment, not in a new process.

Let's compare this with running a script normally:

```
➜  ~ ./script.sh
# This creates a child process.
➜  ~ source script.sh  # or . script.sh
# This runs in the current shell process.
```

This explains why we need to source our .zshrc or .bashrc files when we make changes. If we just executed them as regular scripts, they would:

1. Run in a new process
2. Set up all the environment variables and functions in that new process
3. Exit, taking all those changes with them

Suppose now that `script.sh` has a function named `hello`. We can actually see the function with `declare -f hello`. We can also `type hello` now:

```
hello is a shell function from /user/script.sh
```

By sourcing, we're essentially saying "read these commands and execute them right here, in this shell process." That's why all the changes stick around - they're modifying the current process' environment, not creating a new one.
This ties back to our earlier discussion about builtins and process groups: source itself is a builtin command (try type source), because it needs to operate within the shell's memory space to modify its environment. If it were an external command, it wouldn't be able to modify the parent shell's environment due to Unix's process isolation.

## .zshrc what?

Whenever we start a new shell, it automatically "sources" configuration files, like .zshrc or .bashrc. This has to do with how POSIX understands "interactive shells". From the Unix Reference book:

> When you start a non-login shell, it does not read your .profile, .bash_profile, or .login file (or your .logout file), but it will still read the second shell configuration file (such as .bashrc). This means that you can test changes to your .bashrc by starting another instance of the shell, but if you are testing changes to your .profile or .login, you must log out and then back in to see the results.

Zsh does the same thing. From the manual page (`man zsh`), on the startup/shutdown section:

> Then, if the shell is interactive, commands are read from /etc/zsh/zshrc and then $ZDOTDIR/.zshrc.

I found it disappointing that there are no fun stuff about how the shell handle configuration files, but at least I understand that there is an order to read configuration files depending on the type of the shell: login, non-interactive and interactive shell[^1]. Also, this process is a Unix heritage, and zsh / bash / etc are only being compliant to the POSIX standard.

[^1]: interactive shells are the one that read commands from the user. You can read more about the differences here: https://unix.stackexchange.com/questions/50665/what-are-the-differences-between-interactive-non-interactive-login-and-non-lo.
