+++
date = 2025-10-30
title = "Breaking what a program is"
labels = ["post"]
subjects = ["cpu"]
+++

Where does the kernel draw the line between "program" and "data"? Most of this post is me trying to break what a program is, from the kernel's point of view - taking real programs apart, and handing the kernel things it should not accept - until the rule it is enforcing becomes clear.

If you wanna follow along, you should probably take a look at these: the ELF format is laid out in `man 5 elf`, and the kernel side - who is allowed to run what - lives in `fs/exec.c` and the `fs/binfmt_*.c` files in the kernel source.

Take `ls`, for example: 155kb of machine code. The kernel reads almost none of that to decide *whether* to run it - only the ELF header at the very front. What happens when we copy `ls` and start removing fields from the header?

```
frn@debian:~$ cp /bin/ls myls
frn@debian:~$ readelf -h myls | grep -E 'Entry point|Number of program headers'
  Entry point address:               0x6760
  Number of program headers:         14
```

The program headers tell the kernel what to map into memory; the entry point tells it where to start once it has. Their offsets in the file: the header is a fixed-layout struct, and `man 5 elf` gives the order of its fields. The important thing for this experiment is that the program-header count is at byte 56.

Let's start with the program headers. Our first task is to open the copy, seek to 56, write two zero bytes over the count, then ask `readelf` whether it really went to zero:

```
frn@debian:~$ python3 -c 'f = open("myls", "r+b"); f.seek(56); f.write(b"\x00\x00")'
frn@debian:~$ readelf -h myls | grep 'Number of program headers'
  Number of program headers:         0
```

All 155kb of `ls` is still sitting in the file. But:

```
frn@debian:~$ ./myls
bash: ./myls: cannot execute binary file: Exec format error
```

`ENOEXEC`. With no program headers the kernel cannot tell which bytes are code or where they go in memory, so there is nothing for it to load. Now let's put `ls` back and break the other field instead - the entry point, an eight-byte field 24 bytes into the file:

```
frn@debian:~$ cp /bin/ls myls
frn@debian:~$ python3 -c 'f = open("myls", "r+b"); f.seek(24); f.write(b"\x00" * 8)'
frn@debian:~$ readelf -h myls | grep 'Entry point'
  Entry point address:               0x0
```

This time the program headers are intact, so the kernel loads the file happily - and then jumps to the entry point to start running, which is now zero, where there is no code:

```
frn@debian:~$ ./myls
Segmentation fault
```

It loaded and then died. So the rule looks like this: a program is something the kernel can map into memory and start executing - a segment to load and an address to jump to. And these are only two fields out of 155kb.

Except the entry point is not quite the whole truth. `ls` is dynamically linked, and when you run a dynamically-linked program the kernel does not jump to its entry point at all. It jumps to the *interpreter* - the dynamic linker - and lets it load the libraries and eventually call your code. The interpreter is just another field in the file, a path string, and `readelf` will point it out:

```
frn@debian:~$ readelf -p .interp /bin/ls
  [     0]  /lib64/ld-linux-x86-64.so.2
```

So what if we point it somewhere else? 

```
frn@debian:~$ cat fakeld.s
.global _start
_start:
    mov $1, %rax          # write(
    mov $2, %rdi          #   stderr,
    lea msg(%rip), %rsi   #   msg,
    mov $msglen, %rdx     #   len)
    syscall
    mov $60, %rax         # exit(
    mov $3, %rdi          #   3)
    syscall
msg: .ascii "[fakeld] all your base are belong to us\n"
    msglen = . - msg
frn@debian:~$ gcc -nostdlib -no-pie -o /tmp/fakeld fakeld.s
```

The interpreter path sits at a fixed offset in the file - `readelf -l` lists it as the `INTERP` segment, at `0x394` - so I can overwrite it in place and run the result:

```
frn@debian:~$ cp /bin/ls lshj
frn@debian:~$ python3 -c 'f = open("lshj", "r+b"); f.seek(0x394); f.write(b"/tmp/fakeld\x00")'
frn@debian:~$ readelf -p .interp lshj
  [     0]  /tmp/fakeld
frn@debian:~$ ./lshj
[fakeld] all your base are belong to us
```

`ls` never ran. I did not touch one byte of its code - all 155kb is still there - but the kernel went to the interpreter first, and the interpreter was mine. What a "program" does is not always something inside the program.

Scripts make that idea very clear. A shell script is only text. It is "executable" only because its first line names an interpreter and the kernel hands the file to it. Which means the interprter does not have to be a shell. So let's point it at `cat`:

```
frn@debian:~$ printf '#!/bin/cat\nhello, I am data and code at once\n' > s
frn@debian:~$ chmod +x s && ./s
#!/bin/cat
hello, I am data and code at once
```

The "program" prints itself. If we point the same file at `/bin/true` instead, it does nothing at all - `true` ignores its argument and exits - so what a script *does* is decided entirely by whatever line one points to. but let's push harder, with a script whose interpreter is another script:

```
frn@debian:~$ printf '#!/bin/cat\n' > inner ; chmod +x inner
frn@debian:~$ printf '#!/tmp/sh/inner\npayload\n' > outer ; chmod +x outer
frn@debian:~$ ./outer
#!/bin/cat
#!/tmp/sh/inner
payload
```

The kernel followed the chain - `outer` to `inner` to `cat` - and `cat` printed both files. So what if we point a script at itself?

```
frn@debian:~$ printf '#!/tmp/sh/selfie\n' > selfie ; chmod +x selfie
frn@debian:~$ ./selfie
bash: ./selfie: /tmp/sh/selfie: bad interpreter: Too many levels of symbolic links
```

It followed the chain until it noticed the loop, then gave up with the error it normally uses for symlink loops - though there is not a symlink anywhere here, just a file pointing at itslf. There is a counter, and we hit it. (There is a size limit too: if you make the interpreter line a few hundred characters, the kernel cuts it off at 255. The rule is enforced through a fixed buffer.)

Every wall we hit so far looked like a fixed rule. But where does the list of rules live? It lives in the kernel - in a function that tries the file against each format it knows: `search_binary_handler`. `binfmt_misc` lets you add to it. Here is a file in a format nothing recognizes; it starts with the bytes `ZeroWing`:

```
frn@debian:~$ printf 'ZeroWing\nthe kernel runs me now\n' > note.zerowing
frn@debian:~$ chmod +x note.zerowing
frn@debian:~$ strace -e execve ./note.zerowing
execve("./note.zerowing", ["./note.zerowing"], 0x7ffeb60752c0 /* 20 vars */) = -1 ENOEXEC (Exec format error)
```

`ENOEXEC` again - the kernel has no handler that recognizes this file. Now let's teach it one: any file whose magic is `ZeroWing` should run through `cat`.

```
frn@debian:~$ echo ':zerowing:M::ZeroWing::/bin/cat:' | sudo tee /proc/sys/fs/binfmt_misc/register
frn@debian:~$ cat /proc/sys/fs/binfmt_misc/zerowing
enabled
interpreter /bin/cat
flags:
offset 0
magic 5a65726f57696e67
```

And the same file, not one byte changed, is now a program:

```
frn@debian:~$ strace -e execve ./note.zerowing
execve("./note.zerowing", ["./note.zerowing"], 0x7ffda9111b70 /* 20 vars */) = 0
frn@debian:~$ ./note.zerowing
ZeroWing
the kernel runs me now
```

Wrapping all of this: a 155kb binary with its program headers or its entry point zeroed: not a program. A binary whose interpreter was swapped: runs, but runs the swapped interpreter. A text file that does whatever its first line says, and dies if that line points back at itself. A `ZeroWing` file that was garbage until I registered a handler, and then wasn't.

So a program is not a kind of file. It is a file the kernel has agreed to run - and the agreement has terms. If we break any term, the file stops being a program, whatever is inside it. The line between data and program is in the contract - and the contract is the kernel's to enforce and, if you ask the right way, yours to modify.

One last break. Take a file that satisfies every term we listed: a valid ELF, program headers intact, a real entry point. By the contract, it is a program. Copy `ls` once more and change a single field - `e_machine`, the two bytes that say which CPU the code was built for (offset 18). We flip it from x86-64 to AArch64 and see what happens.

```
frn@debian:~$ cp /bin/ls archmix
frn@debian:~$ python3 -c 'f = open("archmix", "r+b"); f.seek(18); f.write(b"\xb7\x00")'
frn@debian:~$ readelf -h archmix | grep -E 'Type|Machine'
  Type:                              DYN (Position-Independent Executable file)
  Machine:                           AArch64
```

`readelf` reads it without complaint: a valid 64-bit executable, four `LOAD` segments. Nothing we broke earlier is broken here - there is a segment to load and an address to jump to. But:

```
frn@debian:~$ ./archmix
bash: ./archmix: cannot execute binary file: Exec format error
frn@debian:~$ strace -e execve ./archmix
execve("./archmix", ["./archmix"], 0x7fff7df220b0 /* 20 vars */) = -1 ENOEXEC (Exec format error)
```

`ENOEXEC`, on a file that satisfies everything we listed. `e_machine` is part of the ABI: the rules for how code and the processor fit together - instruction encoding, registers, how a syscall is made, etc.. x86-64 instructions mean nothing to an ARM core, so the kernel checks the architecture first, before it maps anything. If the CPU cannot run the code, everything else is irrelevant. 


