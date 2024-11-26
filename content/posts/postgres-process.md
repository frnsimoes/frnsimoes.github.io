+++ 
date = 2024-11-06
title = "What's the 'Postgres server'?"
+++

I Thought I was studying Postgres, but here we go again with operating systems and networking. Jokes aside, Postgres' process architecture is really interesting. A great overview on the topic is Suzuki's explanation of various types of processes, which you can find [here](https://www.interdb.jp/pg/pgsql02/01.html).

- Postgres server process: the "parent" process that manages the database system. It's the thing that has an IP and a port.

- Backend process: It's the entity that reads and writes queries.

- Background process: a process created by the server process to perform various tasks, such as vacuuming, archiving, and replication. Background processes run independently of the client connections.

What I want to understand more today is the Postgres server process. Suzuki once again has an excellent explanation on the topic:

> When you execute the pg_ctl utility with the ‘start’ option, a postgres server process starts up. It then allocates a shared memory area in memory, starts various background processes, starts replication-associated processes and background worker processes if necessary, and waits for connection requests from clients. Whenever it receives a connection request from a client, it starts a backend process. (The started backend process then handles all queries issued by the connected client.)

> A postgres server process listens to one network port, the default port is 5432. Although more than one PostgreSQL server can be run on the same host, each server must be set to listen to a different port number, such as 5432, 5433, and so on.

Let's understand better the key points of this explanation.

**Shared buffers**

Postgres utilizes two types of shared memory, one of which is the classic `fork()` mechanism without `exec()`. When a child process is created in this manner, it shares the memory space of the parent process, but it operates independently from the parent and other child processes. After the `fork()`, any actions performed by the child process, such as handling queries or executing transactions, remain unknown to the parent process. Likewise, the parent (the Postgres server process) can continue executing its tasks, like managing connections or monitoring system health, without the child processes being aware of these actions. This separation creates a level of isolation between the processes, ensuring that each backend process works independently on its respective client connection, while still sharing certain memory resources for efficient data handling.

Because of this isolation, Postgres also utilizes POSIX shared memory[^1]. This is a memory sharing mechanism that allows processes to share memory without the need for a parent-child relationship. This is useful for sharing data between processes that are not directly related, such as the Postgres server process and the background processes that perform tasks like vacuuming, archiving, and replication. By using POSIX shared memory, Postgres can allocate a shared buffer to each process's address space, allowing them to communicate and share data efficiently[^2].

It is important to note that Postgres does not utilize `mmap`, like other databases[^3].

But where is it?

Postgres is actually straightforward with this. The shared buffer can be configured in the postgres.conf.

```
sudo -iu postgres
postgres@frn:~$ psql

psql (15.8 (Debian 15.8-0+deb12u1))
Type "help" for help.

postgres=# SHOW config_file;
               config_file
-----------------------------------------
 /etc/postgresql/15/main/postgresql.conf
(1 row)

postgres@frn:~$ cat /etc/postgresql/15/main/postgresql.conf | grep "shared_buffers"
shared_buffers = 128MB                  # min 128kB
```

So Postgres allocates 128MB to the shared_buffer. What else can we know about it? Let's query the `pg_stat_bgwriter` view to check some things about the background processes.

```sql
 checkpoints_timed | checkpoints_req | checkpoint_write_time | checkpoint_sync_time | buffers_checkpoint | buffers_clean | maxwritten_clean | buffers_backend | buffers_backend_fsync | buffers_alloc |          stats_reset
-------------------+-----------------+-----------------------+----------------------+--------------------+---------------+------------------+-----------------+-----------------------+---------------+-------------------------------
               679 |              12 |                  2630 |                   87 |                 26 |             0 |                0 |               2 |                     0 |          1182 | 2024-10-30 11:37:08.536891-03
(1 row)
```

That's interesting. We can see that the `buffers_checkpoint` is 26. This means that 26 buffers were written to disk in the last checkpoint. The `buffers_clean` is 0, which means that no buffers are clean. The `buffers_backend` is 2, which means that 2 buffers are being used by the backend processes. The `buffers_backend_fsync` is 0, which means that no buffers are being used by the backend processes and are being written to disk.

**Background processes**

Suzuki also says that the Postgres server "starts various background processes", but what are these processes?

There are multiple background processes in Postgres. The most interesting that I found are the `autovacuum`, which cleans up dead rows in tables, and the `checkpoint`, which writes dirty pages to disk.

The `WAL writer` is a really interesting one: it writes the WAL (Write-Ahead Logging) to disk. The WAL is a log of all changes made to the database and is used for crash recovery. One interesting thing about WAL is that it also has a buffer:

```bash
postgres@frn:~$ cat /etc/postgresql/15/main/postgresql.conf | grep "wal_buffers"
#wal_buffers = -1                       # min 32kB, -1 sets based on shared_buffers
```

The WAL records every change made to the database, including inserts, updates, etc., before those changes are permanently written to the actual database files. So, if the database crashes unexpectedly, all recent changes can be replayed (I keep reading this word, but what does it mean in this context?) from the buffer to restore the database to its last consistent state.

**Replication-associated processes**

Suzuki says that the server process starts replication-associated processes. What are these processes?

They are responsible for handling data replication between databases in a cluster. They ensure consistency between them. Postgres servers mainly manage WAL files for streaming replication and logical replication. A WAL sender process is responsible for sending WAL files to the standby server. A WAL receiver process is responsible for receiving the WAL files from the primary server. A WAL writer process is responsible for writing the WAL files to disk.

**Waiting for connection requests from clients**

Besides the process creation topic, this is, for me, the most interesting one. I want to write an isolated text about it. But let's try to understand a little bit more about it.

The Postgres server has an IP and a port. The Postgres server manages a cluster of databases. Databases are identified by their "name", and it's only the Postgres server that has a socket address.

Whenever a client opens a socket and sends a TCP request to the Postgres server socket, it spawns a backend process to handle the request. The backend process parses SQL queries, plans query execution strategies, executes the query, and fetches results; it also handles transaction management and returns the results to the client.

We can query backend processes:

```
postgres=# SELECT pid, datname, usename, application_name, client_addr, backend_start, state
FROM pg_stat_activity;
  pid  | datname  | usename  | application_name | client_addr |         backend_start         | state
-------+----------+----------+------------------+-------------+-------------------------------+--------
   974 |          |          |                  |             | 2024-11-06 18:25:07.26712-03  |
   975 |          | postgres |                  |             | 2024-11-06 18:25:07.267439-03 |
 15486 | postgres | postgres | psql             |             | 2024-11-06 20:38:39.940907-03 | active
   965 |          |          |                  |             | 2024-11-06 18:25:07.170085-03 |
   964 |          |          |                  |             | 2024-11-06 18:25:07.169509-03 |
   973 |          |          |                  |             | 2024-11-06 18:25:07.266529-03 |
(6 rows)
```

One interesting thing is the data transmission between the client and the server. You can monitor a TCP request/response with something like Wireshark, for example, and see how lazily a backend process handles the request. The backend process streams the data, sending the result data as soon as it's ready, without waiting to complete the entire query. In this way, the client can start processing the data as soon as it arrives, without waiting for the entire query to complete.

[^1]: checkout `man shm_open`: shm_open() creates and opens a new, or opens an existing, POSIX shared memory object. A POSIX shared memory object is in effect a handle which can be used by unrelated processes to mmap(2) the same region of shared memory. The shm_unlink() function performs the converse operation, removing an object previously created by shm_open().

[^2]: https://stackoverflow.com/questions/32930787/understanding-postgresql-shared-memory

[^3]: Andy Pavlo has an interesting take on this: https://db.cs.cmu.edu/mmap-cidr2022/
