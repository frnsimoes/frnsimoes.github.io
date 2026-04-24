+++
date = 2024-05-22
title = "Builtins and source"
labels = ["post"]
+++

Understanding how the shell manages environment variables and session state requires understanding builtins, process groups, and memory space. This post traces how these pieces connect.

## Types, builtins

There is a classification in the shell called `builtin`. Some commands are builtin:

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

When a shell runs a command, it does one of two things: execute something available in its own memory space (a builtin), or execute something external (via `execve`).

Let's strace `echo`:

```
➜  ~ strace echo hello | head
execve("/usr/bin/echo", ["echo", "hello"], 0x7ffd741cb2d8 /* 36 vars */) = 0
```

`echo` is a builtin, but `strace` forced the shell to call `/usr/bin/echo` instead. `strace` needs a separate process to attach to - it can't trace something that runs inside the shell's own address space. Let's try to force the builtin:

```
➜  ~ strace builtin echo hello
strace: Can't stat 'builtin': No such file or directory
➜  ~ builtin echo hello
hello
```

We can't strace the builtin because it lives in the same address space as the shell process itself. From the GNU docs:

> Builtin commands are contained within the shell itself. When the name of a builtin command is used as the first word of a simple command (see Simple Commands), the shell executes the command directly, without invoking another program. Builtin commands are necessary to implement functionality impossible or inconvenient to obtain with separate utilities.

There is also a coreutils `echo` at `/usr/bin/echo`. Two implementations of the same command: one lives inside the shell and the other one is external. The builtin exists because some operations - like exporting variables - need to modify the shell's own memory space. An external process can't do that.

## Shell sessions and process groups

Unix uses two types of control over processes: process groups and session ids.

A process group is a collection of related processes. You can signal them all at once:

```
➜ ps -o pid,pgid,comm | grep bash
22851 22851 bash
22852 22851 bash
48233 48233 bash
48234 48233 bash
```

Two process groups here: `22851` and `48233`, each with two processes. A session is a collection of process groups, used for job control and signaling. You can get the session id with `getsid(2)`.

Each process has an environment list. To see every variable in the current process: `declare -x`.

When a process creates a child, it shares its environment list with the child. But you can also set environment variables exclusively for a child: `HELLO='hello' ./script`.

Some useful commands for exploring this: `pstree -aps <PID>` shows the process tree, and `sudo cat /proc/<PID>/environ` shows the environment list of a process.

## Sourcing files

What happens when we `source` a file? When we source (or use `.`, which is equivalent), the shell reads and executes commands from that file in the current shell environment - not in a new process.

Compare:

```
➜  ~ ./script.sh
# Creates a child process.

➜  ~ source script.sh  # or . script.sh
# Runs in the current shell process.
```

This is why we source .zshrc or .bashrc after making changes. If we executed them as regular scripts, they would run in a new process, set up variables and functions there, then exit - taking all changes with them.

If `script.sh` defines a function named `hello`, after sourcing we can inspect it:

```
➜  ~ declare -f hello
➜  ~ type hello
hello is a shell function from /user/script.sh
```

By sourcing, we tell the shell to execute the commands in its own process. The changes persist because they modify the current process' environment, not a disposable child.

This connects back to builtins: `source` itself is a builtin (try `type source`), because it needs to operate within the shell's memory space. If it were an external command, it couldn't modify the parent shell's environment due to Unix process isolation.

## .zshrc

When we start a new shell, it automatically sources configuration files. This follows POSIX rules about interactive shells. From the Unix Reference book:

> When you start a non-login shell, it does not read your .profile, .bash_profile, or .login file (or your .logout file), but it will still read the second shell configuration file (such as .bashrc). This means that you can test changes to your .bashrc by starting another instance of the shell, but if you are testing changes to your .profile or .login, you must log out and then back in to see the results.

Zsh does the same. From `man zsh`:

> Then, if the shell is interactive, commands are read from /etc/zsh/zshrc and then $ZDOTDIR/.zshrc.

There is an order to reading configuration files depending on shell type: login, non-interactive, and interactive[^1]. This is Unix heritage - zsh, bash, and others are being compliant to the POSIX standard.

[^1]: Interactive shells read commands from the user. More on the differences: https://unix.stackexchange.com/questions/50665/what-are-the-differences-between-interactive-non-interactive-login-and-non-lo.
