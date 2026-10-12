+++
date = 2025-12-11
title = "Investigating 108,725 forks"
labels = ["post"]
+++ 

One of the servers was hitting 90% CPU utilization. A few containers running, no alerts. I ssh'ed and found a process with cmd `bash startup.sh` that had been running for 28 minutes. I straced it for a few minutes:

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

108,725 forks and 134,819 wait4 calls. The delta is 26,094 - the exact same number of wait4 errors. Also the same exact number for ioctl and rt_sigreturn. I searched but didn't find the file. Since this process was running, I could read the exact script from file descriptor 255. This was a supervisor process. It created a bunch of children using fork, then waited for them via wait4, and managed their file descriptors and masks.

This happened on the second day of this new job, at 8pm. I burned the machine and started a new one.
