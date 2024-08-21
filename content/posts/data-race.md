+++ 
date = 2024-08-20
title = "Concurrency: data race"
+++

A simple example of a multi-threading program. We have two threads (p1 and p2) that increment a shared variable (counter) 1000 times each.


```c
#include <stdio.h>
#include <pthread.h>

#define EACH_COUNT 1000

volatile int counter = 0;

void* thread_entry(void *arg) {
	for (int i = 1; i < EACH_COUNT; i++) counter++;
	return NULL;
}

int main() {
	pthread_t p1, p2;
	pthread_create(&p1, NULL, thread_entry, NULL);
	pthread_create(&p2, NULL, thread_entry, NULL);

	pthread_join(p1, NULL);
	pthread_join(p2, NULL);

	printf("Final count %d (expected %d)\n", counter, 2 * EACH_COUNT);
}
```

When we try to run this program, the result is always variable and less than the expected 2000. 

The two threads share the same address space in memory. Each one of them has its own stack and heap, but they are in the same "space". In other words, p1 can access the stack and heap of p2. They are not protected from one another.

Each thread has its own program counter (PC), stack pointer (SP) and other general registers, though. 

So, why is the result of this code almost always less than 2000?

The OS has a set of rules do schedule `tasks` (jobs can be processes or threads). One of them is the timer. The OS checks for how long a job is running, and, from time to time, stops the execution of one and starts the execution of another. This is called a context switch.

```bash
Running        Ready       OS
t1             t2
                           interrupt (timer)
t2             t1
```

So, in our program, what really happens?

Here is the assembly code for x86 that shows what's is happening behind the scenes (if you are curious to know how to see the assembly code, just `objdump` the binary):

```assembly
movl: counter, %eax
addl: $1, eax
movl: %eax, counter
```

- The first `movl` (move long) is an instruction that copies the currenct value of the variable `counter` into the `eax` register. So, suppose it's thread 1 running, the first iteration, it's copying the value `1` to the register.

```
counter       eax    
0             0   
```

- `addl` adds the immediate value (in our case, `1`) to the value in the `eax`, resulting in `2`. 

```
counter       eax    
0             1
```

- the second `movl` is the write operating, and moves the value from `eax` to the variable `counter`.

```
counter       eax    
1             1
```

So, what happens if there is a timer interrupt (or maybe another surprise interrupt?) after the `addl` but before the writing `movl`? Well, thread 2 is going to run, the `counter` is still `0`, and the `eax` is `1`.

```
counter       eax    
0             1 
```

Here is what is going to happen when thread 2 runs before the last `movl` from thread 1:

Initial state:
```
counter       eax    
0             1
```

- moves the vlaue of counter (`0`) into the eax:

Initial state:
```
counter       eax    
0             0
```

- adds 1 to the value of eax:

```
counter       eax    
0             1
```

- writes back to `counter`

```
counter       eax    
1             1
```

One thing that at first is hard to understand is why do we have the `eax` register in the between? The value of `counter` is in memory. Accessing the memory is slower (latency) than accessing the register. The use of `eax` as an intermediary is a CPU architecture choice, but it also allows some benefits. One thing that I found really interesting but didn´t have the time to investigate (yet) is the notion of `atomic operations`: some operations need to be done in only one CPU cycle to achieve precision.
