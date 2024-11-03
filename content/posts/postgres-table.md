+++
date = 2024-11-03
title = "Postgres tables on disk"
tags = ["relational database"]
+++

Found a really interesting thing while watching Oz's explanation on postgres tables: we can actually see what's going on inside a table. 

We can find the location of postgres data files by running `SHOW data_directory;` in the psql shell. And the file related to that specific table with the command `SELECT pg_relation_filepath('table_name');`.

By hexdumping it, we can actually see the tables data. 

```
root@frn:/var/lib/postgresql/14/main/base/5# hexdump -C 16388 
00000000  00 00 00 00 60 7e 55 01  00 00 00 00 1c 00 d8 1f  |....`~U.........|
00000010  00 20 04 20 00 00 00 00  d8 9f 4a 00 00 00 00 00  |. . ......J.....|
00000020  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
*
00001fd0  00 00 00 00 00 00 00 00  e0 02 00 00 00 00 00 00  |................|
00001fe0  00 00 00 00 00 00 00 00  01 00 03 00 02 08 18 00  |................|
00001ff0  01 00 00 00 13 00 0f 4d  69 63 6b 65 79 00 00 00  |.......Mickey...|
00002000
```

I also used the Ghex to check more details about the file. 

One thing that I found specially interesting is that for the data to be persisted in a file, I needed to run `checkpoint;` in the psql shell. Before that, the file was empty, and the data was only in memory. When `CHECKPOINT` is executed, all data is flushed to the disk.

Another thing I found really interested: I inserted only one row in the table, but when I run `stat` on the file, it shows that the file has 8192 bytes. Why? Is it the size of the postgres page on disk? Interdb comes to help:

> Inside a data file (heap table, index, free space map, and visibility map), it is divided into pages (or blocks) of fixed length, which is 8192 bytes (8 KB) by default. The pages within each file are numbered sequentially from 0, and these numbers are called block numbers. If the file is full, PostgreSQL adds a new empty page to the end of the file to increase the file size.

Fun exercise to materialize some concepts.
