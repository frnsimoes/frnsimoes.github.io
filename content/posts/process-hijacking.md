+++
date = 2025-12-11
title = "Just checking the CPU usage"
+++ 

Today I finally encountered the infamous process hijacking. A colleague was showing me around our Grafana dashboards - just routine monitoring of our baremetal machines. One caught my eye: a machine with 32GB RAM and top-of-the-line processor was hitting 90% CPU usage. 

That didn't make sense. Only a few containers running, nobody had reported issues, no alerts fired. Maybe someone just ran a big loop and forgot about it. Let me check. 

I started with a simple `ps aux --sort=-%cpu | head -n 10`. Found a process with cmd `bash startup.sh`. Interesting, right? Checked Grafana to see for how long this was running. 28 minutes. Oh, ok. This is recent. Process uptime matched. 


## The process

So I decided to forensic the hell out of this process, starting with syscalls:

```
^Cstrace: Process 3668040 detached
% time     seconds  usecs/call     calls    errors syscall
------ ----------- ----------- --------- --------- ----------------
 75.36   52.698676         390    134819     26094 wait4
 12.27    8.583416          78    108725           fork
  7.42    5.190671           5    926332           rt_sigprocmask
  2.69    1.881557           5    330523    165262 close
  1.17    0.817651           9     82631           pipe
  0.64    0.449359           5     78280           rt_sigaction
  0.24    0.164395           6     26094           rt_sigreturn
  0.21    0.147095           5     26094     26094 ioctl
------ ----------- ----------- --------- --------- ----------------
100.00   69.932820          40   1713498    217450 total
```

This is what I found for a few minutes of stracing this process. 108k forks! Something was spawning child processes like crazy. Let's find this big boy:


```
find . -type f -name "startup.sh"
```

Nothing. So `startup.sh` is executing, but the actual file is not on disk. Tha attacker deleted it. It doesn't matter, because we know that if it's a process, it's on memory. Since we know the PID, let's find out what the Kernel has to say about this


```
readlink /proc/3668040/cwd
/tmp
```

## The culprit

No trace of the file in `/tmp`. No worries, again: it's on memory. I found out that we can check the copy of what's running. Bash creates a special file descriptor for this: fd/255. The attacker had deleted the file after execution, but the Kernel keeps the inode alive while the process is running.

So I cat'ed the fd (`cat /proc/3668040/fd/255`) and saw this monstrous, malicious script. I won't paste it here for security and obvious reasons, but here is what it did:

1. ensures `redisserver` is always running
2. if it detects an interactive session, it kills redisserver (well... it didn't work)
3. kills wget/curl/import
4. kills processes with >90% CPU usage and other well-known malwares (kinsing, c3pool)

This thing was orchestrating against other malware while securing its own existence. I checked for its parent process and found postgres. That's when things clicked - the database was compromised. I opened htop to confirm, and sure enough, three 'postgres - background writer' processes began consuming all available CPU. Something was happening. 

At this point, there were two other engineers in the room with me, and the CTO, who was already losing hope in humanity. I exec'ed into the Postgres container. `\l` showed me a new database: `readme_to_restore`. 

I didn't even read. Everyone understood what was happening. We are using PostgreSQL 11 (I know...), so I checked with a friend, who is a security engineer, if he knew a vulnerability that would remotely execute code. He did: https://cybersrcc.com/2025/02/18/postgresql-flaw-exploited-as-zero-day-in-beyondtrust-breach/. The attack likely started with the PostgreSQL exposed to the internet (port 5432, 0.0.0.0) with weak credentials, allowing the attacker to connect and exploit this CVE.

> The root cause lies in how PostgreSQL handles invalid UTF-8 characters. An attacker can introduce malformed UTF-8 sequences that, when processed by psql, lead to premature termination of a SQL command. This manipulation allows the injection of additional SQL statements or the execution of shell commands via psql’s meta-commands, notably the exclamation mark (!) command, which facilitates operating system shell command execution.

Well, mystery solved. Someone hijacked the Postgres server, remotely executed code, created a script in /tmp, executed a Redis server, and was probably wal logging our pg instance.

Thankfully, the attacker only hijacked the Kong database with routing data. Nothing important was exposed. The whole investigation took around two hours. I started alone, people joined along the way. We sleep better now knowing a complete server compromise was caught simply because someone was curious about high CPU usage.


## Or maybe not

Remember the strace output?

```
 75.36   52.698676         390    134819     26094 wait4
 12.27    8.583416          78    108725           fork
```

108 thousands forks, 134k wait4. This tells me the script was killing other processes. I tried to check Postgres logs: `ls -lth /var/log/postgresql/`, but somehow /var/log/postgresql was also deleted. It's been a few hours since the incident, and Grafana is behaving well. I hope it keeps this way.
