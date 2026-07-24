+++
date = 2025-10-21
title = "Breaking a program"
labels = ["post"]
+++

I want to understand what are the boundaries of what a program is. To do this, I'm going to break `ls`. If you want to follow along, you can take a look at these: the ELF format is laid out in `man 5 elf`, and the kernel side - who is allowed to run what - lives in [`fs/exec.c`](https://elixir.bootlin.com/linux/v7.1/source/fs/exec.c) and the `fs/binfmt_*.c` files in the kernel source.

For a program to run, the kernel only need a few fields: the entry point and program headers. The first one tells the kernel where to jump to start executing the program, and the second what to map into memory.

Let's first copy ls and check a few fields:

```
frn@debian:~$ cp /bin/ls myls
frn@debian:~$ readelf -h myls | grep -E 'Entry point|Number of program headers'
  Entry point address:               0x6760
  Number of program headers:         14
```

For us to break `ls`, we need to find where are these two fields' offsets.`man 5 elf` gives the order of its fields. We start with program-headers in the offset 56:

So, yes, let's start with it. Our first task is to open the copy, seek to 56, write two zero bytes over the count, then ask `readelf` whether it really went to zero:

```
frn@debian:~$ python3 -c 'f = open("myls", "r+b"); f.seek(56); f.write(b"\x00")'
...
  Number of program headers:         0
```

If you try to execute it, you will get "Exec format error", so `execve` gets `-1` and raises ENOEXEC. This happens because, with no program headers, the kernel cannot tell which bytes are code or where they go in memory, so there is nothing for it to load.  

Now we copy `ls` again and break the other field - the entry point, an eight-byte field 24 bytes into the file:

```
frn@debian:~$ python3 -c 'f = open("myls", "r+b"); f.seek(24); f.write(b"\x00" * 8)'
...
  Entry point address:               0x0
```

Execute it. No ENOEXEC because the program headers are intact and the kernel loads the file happily, `execve` returns 0 as well. But when the kernel tries to jump to the entry point and start running, there is no code - so we get a segfault ("killed by SIGSEGV"). Ok, so my first intuition is that a program is something the kernel can map into memory and start executing. If it has a segment to load, it's happy; an address to jump to, also happy. 

 `ls` is dynamically linked: and when we run a dynamically-linked program, the kernel does not jump to its entry point, it jumps to the *interpreter* - the dynamic linker - and lets it load the libraries and eventually call the code. The interpreter is just another field in the file, a path string, which you can see with readelf:

```
frn@debian:~$ readelf -p .interp /bin/ls
  [     0]  /lib64/ld-linux-x86-64.so.2
```

So what if we point it somewhere else? 

```
frn@debian:~$ cat fakeld.s
.global _start
_start:
    mov $1, %rax          # write(stderr, msg, len)
    mov $2, %rdi          
    lea msg(%rip), %rsi   
    mov $msglen, %rdx     
    syscall
    mov $60, %rax         # exit(3)
    mov $3, %rdi          
    syscall
msg: .ascii "[fakeld] all your base are belong to us\n"
    msglen = . - msg
frn@debian:~$ gcc -nostdlib -no-pie -o /tmp/fakeld fakeld.s
```

The interpreter path sits at a fixed offset in the file - `readelf -l` lists it as the `INTERP` segment, at `0x394` - so I can overwrite it in place and run the result:

```
frn@debian:~$ cp /bin/ls lshj
frn@debian:~$ python3 -c 'f = open("lshj", "r+b"); f.seek(0x394); f.write(b"/tmp/fakeld\x00")'
frn@debian:~$ ./lshj
[fakeld] all your base are belong to us
```

`ls` never ran. The kernel went to the interpreter first, and the interpreter was fakeld. 

---

### Scripts

Scripts make that idea very clear. A shell script is only text. It is "executable" because its first line tells the kernel what's the script's interpreter. Let's make this clear by point it to `cat`:

```
frn@debian:~$ printf '#!/bin/cat\nCats: all your base are belong to us\n' > s
frn@debian:~$ chmod +x s && ./s
#!/bin/cat
Cats: all your base are belong to us
```

The "program" prints itself. If we point the same file at `/bin/true` instead, it won't do anything - `true` ignores its argument and exits - so what a script *does* is decided entirely by whatever line one points to. 

It seems we are discovering *rules*. And we really are. These rules live in the kernel, in a function that tries the file against each format it knows: `search_binary_handler`. `binfmt_misc` lets you add more. Take for example a file in a format nothing recognizes; it starts with the bytes `ZeroWing`:

```
frn@debian:~$ printf 'ZeroWing\nthe kernel runs me now\n' > note.zerowing
frn@debian:~$ chmod +x note.zerowing
frn@debian:~$ strace -e execve ./note.zerowing
execve("./note.zerowing", ["./note.zerowing"], 0x7ffeb60752c0 /* 20 vars */) = -1 ENOEXEC (Exec format error)
```

`ENOEXEC` again - the kernel has no handler that recognizes this file. Note that the problem isn't the extension `zerowing`, the issue is that the first line of the file is garbage to the kernel because `ZeroWing` means nothing. 

Now that this is clear, let's teach the kernel one more format: any file whose magic[^1] is `ZeroWing` should run through `cat`. 

```
frn@debian:~$ echo ':zerowing:M::ZeroWing::/bin/cat:' | sudo tee /proc/sys/fs/binfmt_misc/register
```

Now you can `cat` /proc/sys/fs/binfmt_misc/zerowing and see: the interpreter is set to `/bin/cat`. 

We didn't change anything in the file, but it's now a program: 

```
frn@debian:~$ ./note.zerowing
ZeroWing
the kernel runs me now
```

---

### e_machine

Ok, so wrapping all of this so far: a simple binary with its program headers or its entry point zeroed: not a program. A binary whose interpreter was swapped: it runs, but runs the swapped interpreter. A text file that does whatever its first line says, and dies if that line points back at itself. A `ZeroWing` file that was garbage until I registered a handler.

This makes things clear to me. A program is a file the kernel knows how to run. 

One last break. Take a file that has every detail we listed: a valid ELF, program headers intact, a real entry point. By the contract, it is a program. 

But copy `ls` once more. Let's change another field now - `e_machine`. This field represent which CPU the code was built for (offset 18). I changed it from x86-64 to AArch64 to see what happens:

```
frn@debian:~$ cp /bin/ls archmix
frn@debian:~$ python3 -c 'f = open("archmix", "r+b"); f.seek(18); f.write(b"\xb7\x00")'
frn@debian:~$ readelf -h archmix | grep -E 'Type|Machine'
  Type:                              DYN (Position-Independent Executable file)
  Machine:                           AArch64
```

`readelf` reads it without any issues: a valid 64-bit executable with four `LOAD` segments. We have a valid entry point too. But when I try to run it, `ENOEXEC` again. `e_machine` is part of the ABI: rules for how code and the processor work together - instruction encoding, registers, how a syscall is made, etc. This also means x86-64 instructions are not valid to an ARM core, for obvious reasons. So the kernel checks the architecture first, before it maps anything. If the CPU cannot run the code, everything else is irrelevant.

---

### June 2026 update

Since I wrote this article, I've read multiple interesting materials exploring files and programs. Two of them are simply great, and I highly recommend if this got you interested and you want to dig deeper.

- [Ange Albertini](https://github.com/corkami/docs/blob/master/talks.md#file-formats) - Funky file formats CCC 2014 is pure gold.
- [Brian Raiter](https://muppetlabs.com/~breadbox/software/tiny/teensy.html)  - How to compose from scratch an ELF file the kernel has agreed to run. 

[^1]: The magic field is the hex for ASCII ZeroWing. `binfmt_misc` entry matches any file whose first 8 bytes are ZeroWing (offset 0) and runs through `/bin/cat`. In this case, the magic field is `5a65726f57696e67`


