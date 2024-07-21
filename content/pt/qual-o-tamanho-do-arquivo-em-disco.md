+++ 
date = 2024-04-01
title = "Qual é o tamanho de um arquivo em disco?"
+++

Tenho brincado um pouco com o sistema operacional e arquivos.

Encontrei o comando stat do POSIX. Na manpage:

>the stat utility displays information about the file pointed to by file.

Estou mais interessado em duas das informações do `stat`: Block e Block IO:

Experimente:

```
root@d6e5e8ac056e:/code# stat tmp
File: tmp
Size: 0               Blocks: 8          IO Block: 4096   regular file
Device: 0,67    Inode: 397692      Links: 1
Access: (0644/-rw-r--r--)  Uid: (    0/    root)   Gid: (    0/    root)
Access: 2024-06-22 16:43:42.909805004 +0000
...
```
`tmp` é um arquivo vazio. `Blocks` é 8 e IO Block é `4096`.

```
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

O que aconteceria se um ou mais byte fosse adicionado no arquivo tmp?

```
root@d6e5e8ac056e:/code# echo -n '.' >> tmp
root@d6e5e8ac056e:/code# stat tmp
File: tmp
Size: 4097            Blocks: 16         IO Block: 4096   regular file
Device: 0,67    Inode: 397692      Links: 1
Access: (0644/-rw-r--r--)  Uid: (    0/    root)   Gid<LeftMouse>: (    0/    root)
Access: 2024-06-22 16:52:42.909805004 +0000
...
```

Agora temos `Blocks: 16`. O OS alocou 8 para um arquivo com 4097 bytes.

Por que 8 blocks?

8 blocks é uma unidade de medidaa. Blocks são contados em unidades de 512 bytes.


**Qual é o tamanho do arquivo em disco?**

Se o arquivo tem Size: 2, digamos, e o OS alocou 8 blocks (`8*512`) para ele, o tamanho do arquivo em disco é de 4096 bytes.

Se o arquivo tem Size: 4097, e o OS alocou 16 blocks (`16*512`), o tamanho do arquivo em disco é de 8192 bytes.

```
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
