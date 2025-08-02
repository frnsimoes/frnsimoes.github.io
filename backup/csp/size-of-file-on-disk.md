+++
date = 2024-04-02
title = "What's the size of a file on disk?"
regular = true
+++

From manpage: 
>the stat utility displays information about the file pointed to by file.

I'm mostly interested in two of the metadata information: Block and Block IO:

Experiment:
```shell
root@d6e5e8ac056e:/code# stat tmp
File: tmp
Size: 0               Blocks: 8          IO Block: 4096   regular file
Device: 0,67    Inode: 397692      Links: 1
Access: (0644/-rw-r--r--)  Uid: (    0/    root)   Gid: (    0/    root)
Access: 2024-06-22 16:43:42.909805004 +0000
...
```

`tmp` is an empty file, the `Blocks` is 8 and IO Block is `4096`. 

```bash
cat /dev/urandom | head -c 4096 > tmp

stat tmp

root@d6e5e8ac056e:/code# stat tmp
File: tmp
Size: 4096            Blocks: 8          IO Block: 4096   regular file
Device: 0,67    Inode: 397692      Links: 1
Access: (0644/-rw-r--r--)  Uid: (    0/    root)   Gid: (    0/    root)
Access: 2024-06-22 16:52:42.909805004 +0000
...
```

What would happen if one more byte was added to the tmp file?

```bash
root@d6e5e8ac056e:/code# echo -n '.' >> tmp
root@d6e5e8ac056e:/code# stat tmp
File: tmp
Size: 4097            Blocks: 16         IO Block: 4096   regular file
Device: 0,67    Inode: 397692      Links: 1
Access: (0644/-rw-r--r--)  Uid: (    0/    root)   Gid<LeftMouse>: (    0/    root)
Access: 2024-06-22 16:52:42.909805004 +0000
...
```

Now we have `Blocks: 16`. The OS "allocated" (virtualized?) 8 new blocks for a file with 4097 bytes.

Why 8 blocks?

8 blocks is a measurement unit. Blocks are counted in 512 bytes unities.


**What is the size of the file on disk?**

If the file has Size: 2, say, and the OS allocated 8 blocks (`8*512`) for it, the size of the file on disk is 4096 bytes.

If the file has Size: 4097, and the OS allocated 16 blocks (`16*512`), the size of the file on disk is 8192 bytes.


