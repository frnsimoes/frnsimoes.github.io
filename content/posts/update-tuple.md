+++ 
date = 2024-11-20
title = "What happens when a row is updated?"
tags = ["OS theory and fun"]
+++

When we update a tuple in a page, a tuple-oriented dbms does the following steps:

- check page directory to find location of the page;
- retrieve the page from disk if it's not in memory;
- find the offset of the page;
- marks existing tuple as deleted and inserts new data.[^1]

Let's understand this better with a simple `test` table in Postgres.


```
postgres=# insert into test (value) values ('t1');
INSERT 0 1
postgres=# insert into test (value) values ('t2');
INSERT 0 1
postgres=# select ctid, value from test;
 ctid  | value
-------+-------
 (0,1) | t1
 (0,2) | t2
(2 rows)
```

Here we have a table `test` with a column `value`. We inserted two tuples into the table with values `t1` and `t2`. The `ctid` column is a pseud column. The first number indicates the page the tuple is in; the second number represents the offset of that tuple in that specific page. Based on this information, we know that the two inserted tuples are in the page `0`, and that `t1` has the offset `1` and `t2` has the offset `2`.  


Now let's try to update `t2`.

```
postgres=# update test set value = 't2n' where value = 't2';
UPDATE 1
postgres=# select ctid, value from test;
 ctid  | value
-------+-------
 (0,1) | t1
 (0,3) | t2n
(2 rows)
```

Postgres didn't update the data in the second offset. Instead, it deleted that tuple, and inserted a new one at the bottom of the page, hence the offset `3` for the inserted tuple. `VACUUM FULL`[^2] will also move the `ctid`.

Let's see what happens:

```
postgres=# select ctid, value from test;
 ctid  | value
-------+-------
 (0,1) | t1
 (0,3) | t2n
(2 rows)

postgres=# delete from test where value = 't1';
DELETE 1
postgres=# select ctid, value from test;
 ctid  | value
-------+-------
 (0,3) | t2n
(1 row)

postgres=# vacuum full verbose test;
INFO:  vacuuming "public.test"
INFO:  "public.test": found 2 removable, 1 nonremovable row versions in 1 pages
DETAIL:  0 dead row versions cannot be removed yet.
CPU: user: 0.00 s, system: 0.00 s, elapsed: 0.00 s.
VACUUM
postgres=# select ctid, value from test;
 ctid  | value
-------+-------
 (0,1) | t2n
(1 row)
```

**But why Postgres handles updates this way?**

Postgres uses Multi-Version Concurrency Control (MVCC) to handle concurrent transactions. When a tuple is updated, the old version of the tuple is kept in the page, and the new version is inserted at the bottom of the page. This way, the old version of the tuple is still available for other transactions that might be using it.

Postgres keeps track of the old version of the tuple using the `xmin` and `xmax` columns. When a tuple is updated, the `xmax` column is set to the transaction id of the transaction that updated the tuple. This way, Postgres knows that the tuple is no longer valid and should not be used by other transactions.

```
postgres=# CREATE EXTENSION pageinspect;
postgres=# SELECT lp as tuple, t_xmin, t_xmax, t_field3 as t_cid, t_ctid
                FROM heap_page_items(get_raw_page('test', 0));
 tuple | t_xmin | t_xmax | t_cid | t_ctid
-------+--------+--------+-------+--------
     1 |    907 |    912 |     0 | (0,3)
     2 |    910 |    911 |     0 | (0,2)
     3 |    912 |      0 |     0 | (0,3)
(3 rows)
```

Here we can see the two tuples we deleted before, and the updated tuple. 

Just to make sure all things make sense, let's check the current state of the table:

```

postgres=# select ctid, value, xmax from test;
 ctid  | value | xmax
-------+-------+------
 (0,3) | t2n  |    0
(1 row)
```

Postgres' [concurrency model](https://www.interdb.jp/pg/pgsql05.html) is certainly interesting, and I plan to investigate it more deeply in the future.


[^1]: https://www.youtube.com/watch?v=IHtVWGhG0Xg&list=PLSE8ODhjZXjYDBpQnSymaectKjxCy6BYq
[^2]: https://www.postgresql.org/docs/current/ddl-system-columns.html#DDL-SYSTEM-COLUMNS-CTID
