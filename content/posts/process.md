+++
date = 2024-06-18
title = "Forking around with fork()"
+++ 

The way Unix systems create a process is really not intuitive. At first, I would imagine that creating a process in the OS would be as simple as calling a systemcall `create`, or something like that. 

But, in reality, the genesis of a process creation in Unix involves creating a hierarquical tree of processes.

The running program you are using to create a new process is a process itself, so the way you can create a new process is by creating a child of the current process.

The API involves three steps: fork(), execute(), and then wait(). A simple example:

```
#include <stdio.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>

int main() {
    pid_t pid = fork();

    if (pid < 0) {
        perror("Fork failed");
        return 1;

    } else if (pid == 0) {
        printf("World\n");

    } else {
        wait(NULL);
        printf("Hello\n");
    }

    return 0;
}
```

First, we call `fork()` to create a child process. If it's pid (the returned value) is `< 0`, an error occurred. If it's `== 0`, we are in the child's realm, else, in the parent's realm. As far as I know, if we don't call `wait()` in the parent's realm, there is no way to know what is going to be executed first (`Hello\n` or `World\n`), because the order of executing depends on the implementations of the operating system scheduler. But, by waiting, the parent process waits for the child's PID return.

With this simple process, you can actually build a simple shell: the shell itself is a process, so by creating and executing a new processes within a shell (say you type `yes` on your terminal and press `return`), you are actually creating and executing a process that is a child to the bash / zsh / etc process. Here is a really simples [implementation of a shell].

This model can be odd, some really love it, some really hate it. There is a famous (at least famous along us nerds) article accusing fork to be a bad thing in an operating system, if you are curious: [a fork() in the road]. 

The OS also displays the relations of the current process in your operating system in a tree. Try calling `pstree` in your terminal.

Although this API may be odd, I like what the authors of [OSTEP] say: 
> the separation of fork() and exec() is essential in building a UNIX shell, because it lets the shell run code after the call to fork() but before the call to exec(); this code can alter the environment of the about-to-be-run program, and thus enables a variety of interesting features to be readily built.

One example would be the following:

```
int main(int argc, char *argv[]) {
	int rc = fork();
	if (rc < 0) {
		// fork failed; exit
		fprintf(stderr, "fork failed\n");
		exit(1);
	} else if (rc == 0) {
		// child: redirect standard output to a file
		close(STDOUT_FILENO); 
		open("./p4.output", O_CREAT|O_WRONLY|O_TRUNC, S_IRWXU);
                // exec is called
```

In this simple example, we call close[^1] on the standard out file descriptor and open a file. By doing this, we could manipulate the child process to output something into the open file.


[implementation of a shell]: https://github.com/frnsimoes/computer-science-studies/blob/main/operating-systems/programs-and-processes/basic-shell/shell.c
[a fork() in the road]: https://www.microsoft.com/en-us/research/uploads/prod/2019/04/fork-hotos19.pdf
[OSTEP]: https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-api.pdf

[^1]: from man page: The close() call deletes a descriptor from the per-process object reference table.


