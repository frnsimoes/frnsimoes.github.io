+++
date = 2025-06-30
title = "What is a program?"
+++

This is [Remzi Arpaci](https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-intro.pdf) being a cool teacher:

> The definition of a process, informally, is quite simple: it is a running program.

The first time I read this I thought: Okay, Remzi, but what the heck is a program? Months go by and I explore filesystems, inodes, syscalls, etc., etc., and still don't truly understand what a program is. "A bunch of bytes". "Something on disk". I don't know! Don't ask me! It's a thing you run!

I got angry and decided to start from the absolute basics and work my way up.

## What is a program?

A program is a bunch of bytes sitting somewhere on disk, storage, whatever. It's there, in a persistent layer, waiting for something to happen. The important part in the definition is the "waiting for something to happen". The program exist so something else can happen. So the first thing we can be sure is: a program is what can be run by the machine.

Alright. Is `ls` a program? Hmm. We can execute it, right? So it probably is. Let's try to understand this in more detail:

```
frnsh@debian:~$ file /bin/ls
/bin/ls: ELF 64-bit LSB pie executable, ARM aarch64, version 1 (SYSV), dynamically linked, interpreter /lib/ld-linux-aarch64.so.1, BuildID[sha1]=87a7eadc711cd002f7b00ba923179e5713498159, for GNU/Linux 3.7.0, stripped
```

`/bin/ls` is an ELF executable. What is this? Let's search in the manual page:

```
frnsh@debian:~$ man elf
DESCRIPTION
       The header file <elf.h> defines the format of ELF executable binary files.  Amongst these files are normal executable files, relocatable object files, core files, and shared objects.
```

Ok, so we know that there is a format called "ELF" that the operating system knows about. What can we do with ELF files? Can we discover any more details about this file given that it's an ELF file? Yes! We can use `readelf` to inspect it:

```
frnsh@debian:~$ readelf -h /bin/ls
ELF Header:
  Magic:   7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00
  Class:                             ELF64
  Data:                              2's complement, little endian
  OS/ABI:                            UNIX - System V
  Machine:                           AArch64
  Entry point address:               0x65c0
  Start of program headers:          64 (bytes into file)
  Start of section headers:          197720 (bytes into file)
```

This is actually pretty interesting. We have information about the OS, the machine, and even the entry point address of that program. A binary, then, has lots of information about how to execute it, what architecture it's for, what's the entry point of the program, and other details. The information about the entry point of the program is really interesting, but let's leave it for another time.

## But what about scripts, like Python scripts?

Are they programs too? Let's create a simple Python script that has a `#!/usr/bin/python3` shebang at the top, and prints "hello". And then let's find out how the OS classifies this program:

```
frnsh@debian:~$ file sh.py
sh.py: Python script, ASCII text executable
```

So, is this a program? What happens when we execute it? Here's what I found fascinating: the kernel is basically doing pattern matching. It reads the first few bytes of the file, sees the shebang (`#!`) at the top, and thinks "ah, this isn't a binary I can execute directly - it's instructions for another program."

So the kernel becomes a middleman. It sees `#!/usr/bin/python3`, extracts that path, and essentially transforms our `./sh.py` command into `/usr/bin/python3 sh.py`. The actual program that gets executed is the Python interpreter; our script is just data fed to it.

This happens inside the kernel through something called `search_binary_handler` - a function that tries different "handlers" for different file types until it finds one that knows what to do with our file.


## But back to the binary program: what exactly is inside /bin/ls?

If we try to `cat` /bin/ls, we will see something like this:

```
frnsh@debian:~$ cat /bin/ls | head
LFe@X@8
        @@@$$$c,yK!cr
Uj<{D+W              p9:V$d%>~G Xk"UcQltcwba3j*
```

What's happening behind the scenes is this: our terminal is trying to be helpful and decode the output as UTF-8 text. But the truth is that terminals are kind of dumb. They'll try to interpret any sequence of bytes as text, even when those bytes represent machine instructions, memory addresses, or other binary data.

Something similar is trying to read a JPEG file as if it were a text document - you'll get garbage because you're using the wrong decoder. The same sequence of bytes can mean completely different things depending on how you interpret them: UTF-8 text, a 32-bit integer, ARM assembly instructions, or something else entirely.

Fortunately, the shell has a small utility called `strings`, which can read a binary and print to stdout the parts of the binary that can be interpreted as printable ASCII/UTF-8 text. We can also translate the program's bytes to hexadecimal using `hexdump -c` or even read the actual assembly instructions using `objdump -d`.

## Can we create a fake ELF executable?

But right now I'm more interested in another question: what if I create a fake ELF file by adding by hand the ELF magic number, will it become a ELF executable? Remember that the `search_binary_handler` reads the ELF magic numbers to check if the file is an ELF file. Well, let's try it.

```
# create file with ELF "header"
frnsh@debian:~$ printf '\x7fELF' > fake_elf
frnsh@debian:~$ file fake_elf
fake_elf: ELF
```

Interesting. This confirms that `file` actually only reads the header and outputs a summary of what's there. `readelf` checks deeper into the structure to see what it can extract from the file:

```
frnsh@debian:~$ readelf -a fake_elf
readelf: Error: fake_elf: Failed to read file's magic number
```

If we echo a magic number to fake_elf, we get the subsequent error (now it finds the magic number, but not the file header).

```
frnsh@debian:~$ echo -e '\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x3e\x00' > fake_elf
frnsh@debian:~$ readelf -a fake_elf
readelf: Error: fake_elf: Failed to read file header
```

Now comes the fun part: will the kernel actually try to execute our fake ELF? Let's make it executable and see what happens:

```
frnsh@debian:~$ ./fake_elf
-bash: ./fake_elf: cannot execute binary file: Exec format error
```

Perfect! This is exactly what I expected. The `file` command was fooled by our magic number, but the kernel is much more thorough. When we try to execute it, the kernel's loader does deeper validation and realizes our file is garbage.

We can see this happening with `strace`:

```
frnsh@debian:~$ strace -e execve ./fake_elf
execve("./fake_elf", ["./fake_elf"], 0xffffd3072180 /* 22 vars */) = -1 ENOEXEC (Exec format error)
strace: exec: Exec format error
```

The `ENOEXEC` error tells us the kernel tried to execute our file but gave up when it realized the format was invalid. This shows an important distinction: having the correct magic number makes a file *identifiable* as an ELF format, but creating a *functional* executable requires much more - proper headers, sections, program segments, and valid machine code.

Conceptually, we could create a legitimate ELF executable by hand, but it would require writing assembly code and carefully constructing all the required ELF structures. The kernel doesn't mess around when it comes to execution.

## Now I get you, Remzi

A program isn't just "bytes on disk", it's *structured data* with very specific formats and protocols. It's an agreement with the kernel. The kernel also has multiple layers of validation, and it's surprisingly picky about what it will and won't execute. The difference between `file` being fooled by our fake ELF and the kernel rejecting it shows just how thorough these checks are.

I also learned that the boundary between "program" and "data" is blurrier than I thought. A Python script is just text data until the kernel sees that shebang and decides to feed it to an interpreter. A binary is just bytes until the ELF loader validates its structure and maps it into memory.
