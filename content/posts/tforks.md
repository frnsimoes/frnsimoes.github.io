+++
date = 2025-12-11
title = "108,725 forks"
labels = ["post"]
subjects = ["cpu", "production"]
+++ 

First week at a new job. A colleague was showing me around our Grafana dashboards, just routine monitoring of the baremetal machines. One caught my eye: a machine with 32GB RAM and a top-of-the-line processor was hitting 90% CPU. A few containers running, no alerts, and nobody had reported anything.

I found a process with cmd `bash startup.sh` that had been running for 28 minutes.

I straced it for a few minutes:

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

108,725 forks and 134,819 wait4 calls. The delta is 26,094 - exactly the number of wait4 errors. Also the same exact number for ioctl and rt_sigreturn! The script was forking children and waiting on processes it didn't create.

I looked for the file:

    find . -type f -name "startup.sh"

Nothing. The process was deleted after execution. But the kernel keeps the inode alive while the process holds it open, and bash opens the script on fd 255.

    cat /proc/3668040/fd/255

It was a cryptominer wrapper. It kept a fake `redisserver` running, and if it detected an interactive session it tried to kill the miner to hide itself. It killed wget, curl, and import so nobody could easily download tools. It killed processes above 90% CPU and known malware names - kinsing, c3pool - so it wouldn't have to share the machine.

The strace told the whole story before I ever read the script. 108k forks to keep its own children alive, and 26k extra wait4s to reap competing processes it was killing. The numbers didn't add up because the script was actually hunting.

I checked for Postgres logs, but /var/log/postgresql was deleted.

We burned the machine.
