+++
date = 2025-01-05
title = "source and export diff"
+++

Non-interactive shells don't load initialization files, so `bash -c 'declare -f'` doesn't output anything. But we can source it: `bash -c 'source ~/.bashrc; hello'`. Or even: `bash -c 'hello() { echo "hi"; }; declare -f'`. 

It's all about memory share in shell modes:

- `source` changes only affect current shell memory. 

- `export` marks variables to be passed to child processes.

Subtile difference that can save us lots of debugging time.
