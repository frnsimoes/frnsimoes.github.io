+++ 
date = 2024-05-29
title = "What's the size of a file on disk?"
+++

I've been playing a little bit with the OS and files.

I found the `stat` posix command. From manpage: 
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

```shell
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

```shell
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

```c
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <stdio.h>
#include <limits.h>
#include <stdlib.h>

#define ONE_MEG 1024 * 1024


int main() {
	int f = open("/tmp/foo", O_WRONLY | O_TRUNC);

	blkcnt_t prior_blocks = -1;
	struct stat st;

	for (int i = 0; i < ONE_MEG; i++) {
		write(f, ".", 1);
		fstat(f, &st);

		if (st.st_blocks != prior_blocks) {
			printf("Size: %lld, blocks: %lld, on disk: %lld\n", st.st_size, st.st_blocks, st.st_blocks * 512);
			prior_blocks = st.st_blocks;
		}
	}

	close(f);
	return 0;
}
```
