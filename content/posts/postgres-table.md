+++
date = 2024-11-03
title = "Postgres tables on disk"
tags = ["relational database"]
+++

Found a really interesting thing while watching Oz's explanation on postgres tables: we can actually see what's going on inside a table.

I created a simple table, `foo`, than inserted two records in it.

```
postgres=# create table foo (id int, age smallint, name varchar(100));
CREATE TABLE
```

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

A page inside a file has three types of value: 1. the heap tuple (the data itself); 2. the line pointer (a pointer to each tuple); 3. the header data, containing general information about the page[^1].

So each new tuple is stacked in the bottom of the page. In my case, if I open the file with a hex editor like `ghex`, I can see my data at the end of the file.

Postgres also stores a `TID` (tuple identifier). The TID has two values: the block number of the page that contains the tuple, and the offset number of the line pointer that points to the tuple. I don´t know yet, since it's the beginning of my studies on postgres, but I believe that the `TID` is used in the algorithm of efficient fetching data? Probably. 

Finally, I was thinking about what happens when postgres needs to read some data and fetch it into memory. What if the table is gigantic, what does it do? Reading everything into memory would be tremendously inefficient, right? 

To answer both questions temporarily (I will certainly come back to this problem), I found an excellent explanation: "the scanning is done through the buffer cachee. The system uses a small buffer ring to prevent larger tables from pushing potentially useful data from the cache. When another process needs to scan the same table, it joins the buffer ring, saving disk read times"[^2].

There are certainly big questions that needs to be answered, but the point of this text is clearly done: we can actually access the file in which postgres stores data (I found it really cool), and the layout of the page is also an interesting thing: postgres employs a technique to store pointers to tuples, knows the offset of the data, and stores the data at the bottom of the file -- which is also a cool detail, since if the data was at the bottom of in the beginning, so many bytes would need to be shifted when new data arrived. 

[^1]: https://www.interdb.jp/pg/pgsql01/03.html
[^2]: https://postgrespro.com/blog/pgsql/5969403

