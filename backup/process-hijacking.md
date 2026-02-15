+++
date = 2025-12-11
title = "/proc/fd/255 and wait4 > fork"
+++ 

This happened at my first week at this new job. It's basically a story about a funny way I found out we had been hacked. 

A colleague was showing me around our Grafana dashboards - just routine monitoring of our baremetal machines. One caught my eye: a machine with 32GB RAM and top-of-the-line processor was hitting 90% CPU usage. That didn't make sense. Only a few containers running, nobody had reported issues, no alerts fired. Maybe someone just ran a big loop and forgot about it? Let me check. 

I checked and found a process with cmd `bash startup.sh`. Interesting. It's been running for 28 minutes. Oh, ok. This is recent. 

## The process

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


This is what I found for a few minutes of stracing this process. 108k forks! But take a look at the wait4 calls: 134k. Errors: 26k, excactly the delta between wait4 calls - fork calls. Something is strange.

```
find . -type f -name "startup.sh"
```

Nothing. So `startup.sh` is executing, but the actual file is not on disk. Was the file deleted? It doesn't matter. Let's find out what the Kernel has to say about this


```
readlink /proc/3668040/cwd
/tmp
```

## The culprit

No trace of the file in `/tmp`. I searched and found out that, if it's a script running, we can find it at /fd/255! Bash creates a special file descriptor for this. The file was probably deleted after execution, but the Kernel keeps the inode alive while the process is running.

So I cat'ed the fd (`cat /proc/3668040/fd/255`) and saw this monstrous, malicious script. I won't paste it here for security and obvious reasons, but here is what it did:

1. ensures `redisserver` is always running
2. if it detects an interactive session, it kills redisserver (well... it didn't work)
3. kills wget/curl/import
4. kills processes with >90% CPU usage and other well-known malwares (kinsing, c3pool)

Well, mystery solved. Someone hijacked the Postgres server, remotely executed code, created a script in /tmp, executed a fake "redisserver", and was probably wal logging our pg instance.

We got rid of the compromised machine, but the wait4 > fork kept bugging me. Take a second look at the strace summary: 26094 wait4 errors. But: 26094 `ioctl`, and 26094 `rt_sigreturn`. What?



108 thousands forks, 134k wait4. This tells me the script was killing other processes. I tried to check Postgres logs: `ls -lth /var/log/postgresql/`, but somehow /var/log/postgresql was also deleted. It's been a few hours since the incident, and Grafana is behaving well. I hope it keeps this way.
