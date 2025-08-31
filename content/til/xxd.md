+++
date = 2025-05-25
title = "xxd(1) is a neat tool"
+++

Found out about a cool tool today: `xxd(1)`. Basically, it can help you convert a hexdump file into binary or vice versa. For example:

```
➜   head -c 100 /dev/urandom > out.bin
➜   cat out.bin
5O0!3<[N
                R4DT'{SC95#Rd5b62i^5u(OcD"/MrJBUZ%
``` 

Now let's hexdump it:

```
➜  hexdump -C out.bin > out.hex
➜  cat out.hex
00000000  35 e2 4f 30 21 b4 33 e2  c8 af b9 3c 5b ba 4e 0b  |5.O0!.3....<[.N.|
00000010  09 f6 52 16 34 11 44 54  85 96 b6 00 27 a2 7b 04  |..R.4.DT....'.{.|
...
```

And then use xxd(1) to convert it back:

```
➜   xxd -r out.hex out2.bin
➜   cat out2.bin
5O0!3   R4DTSd5b65u(Մ/MZ%
```

When we inquiry the OS to know what are those files, we get:

```
➜   file out.bin out.hex out2.bin
out.bin:  data
out.hex:   ASCII text
out2.bin: data
```
