Exploring locks.

```c
#include <stdio.h>
#include <pthread.h>

#define EACH_COUNT 1000

pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;

volatile int counter = 0;

void* thread_entry(void *arg) {
	for (int i = 1; i < EACH_COUNT; i++) {
    pthread_mutex_lock(&lock);
        counter++;
    pthread_mutex_unlock(&lock);
    }
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

Scenario: Two threads: T1 and T2. T1 -> Lock -> running, but at some point, an interrupt occurs. T2 tries to get hold of the lock, but it is stuck. If another interrupt occurs in the same context, the result will be the same, no matter how many times T2 tries to get hold of the lock (because of the interrupt). T2 can only take hold when `unlock()` is called. 

How to build a lock, say, a "Spin Lock"?
- First we need a state: lock held (acquired) or free (not acquired).
- We could create a `lock` variable with values `0` (true) and `1` (false): `int lock;`

```c
struct mutex {
    int lock;
}

void mutex_init (mutex *m) {
    m->lock = 0;
}

void mutex_lock (mutx *m) {
    while (m->lock == 1) {
        ;
        m->lock = 1;
    }
}

void mutex_unlock (mutex *m) {
    m->lock=0;
}

```

Goals:
When local is not held (free)
    pthread_mutex_lock() -> should return immediately and lock should become held
When lock is held
    pthread_mutex_lock() -> thread should get stuck here (until lock can be acquired)

The problem with this implementation is that two threads with `0` can enter the loop inside `mutex_lock`, resulting in two threads acquiring the lock simultaneously. For this reason, we need a more powerful instruction from the hardware. "Test and set instruction" or "atomic exchange". 

```c
int TestAndSet(int *old_ptr, int new) {
    int old = *old_ptr;
    *old_ptr = new;
    return old;
}

void mutex_lock (mutx *m) {
    while (TestAndSet(&mutex->lock, 1) {
        ;
    }
}
```

1. **Thread T1 Acquires the Lock**:
   ```markdown
   lock(0,1)     old      new     unlock
   0 T&S(0, 1)   0        1       ---
   ```
   - T1 calls `TestAndSet(&m->lock, 1)`.
   - `TestAndSet` returns `0` (old value), and sets `m->lock` to `1`.
   - T1 acquires the lock.

2. **Thread T2 Tries to Acquire the Lock**:
   ```markdown
   lock(0,1)     old      new     unlock
   0 T&S(1, 1)   1        0       ---
   ```
   - T2 calls `TestAndSet(&m->lock, 1)` while T1 is holding the lock.
   - `TestAndSet` returns `1` (old value), and `m->lock` remains `1`.
   - Since `TestAndSet` returned `1`, T2 will spin-wait (not acquire the lock).
   

The major problem with spinning lock is that when T2 is trying to access the critical section that is held by T1, it will spin, and spin, and spin, it will try to access the critical section every time an interrupt occurs, only to find out that the value didn´t change, and it can't take hold of the lock.

Even more: what happens when a context switch occurs in a critical section, and threads start to spin endlessly, waiting for the interrupted (lock-holding) thread to be run again? (Remzi)


One possible solution is the ticket lock. It is a fair lock, where threads are served in the order they arrive. 

```c
int fetch_and_add(int *addr) {
    int old = *addr;
    *addr = addr + 1;
    return old;
}

typedef struct __lock_t {
    int ticket;
    int turn;
} lock_t;

void lock_init(lock_t *lock) {
    lock->ticket = lock->turn = 0;
}

void acquire(lock_t *lock) {
    int myturn = fetch_and_add(&lock->ticket);
    while (lock->turn != myturn) {
        ;
    }
}

void release(lock_t *lock) {
    lock->turn = lock->turn + 1;
}
```

Ticket Lock is trying to solve the fairness/starvation problem.

1. **Thread T1 calls `acquire(lock_t *lock)`**:
    - `fetch_and_add(&lock->ticket)` is called, which increments `lock->ticket` and returns the old value (which is `0` for T1).
    - T1 sets `myturn` to `0`.
    - T1 enters a `while` loop that spins until `lock->turn` equals `myturn` (which is `0`). Since `lock->turn` is initially `0`, T1 immediately exits the loop and acquires the lock.

2. **Thread T1 performs its critical section**:
    - T1 does whatever work it needs to do while holding the lock.

3. **Thread T1 calls `release(lock_t *lock)`**:
    - T1 increments `lock->turn` by `1`, setting it to `1`.
    - This action effectively releases the lock, allowing the next thread in line (T2) to acquire it.

4. **Thread T2 calls `acquire(lock_t *lock)`**:
    - `fetch_and_add(&lock->ticket)` is called, which increments `lock->ticket` and returns the old value (which is `1` for T2).
    - T2 sets `myturn` to `1`.
    - T2 enters a `while` loop that spins until `lock->turn` equals `myturn` (which is `1`). Since T1 has already incremented `lock->turn` to `1`, T2 immediately exits the loop and acquires the lock.

The advantage of the ticket lock is that it is fair. Threads are served in the order they arrive.

So there are two hardware primitives that address the concurrency problem: exchange (xchg) and fetch_and_add.

**The role of OS in this**

The OS is interested in the concurrency problem. It might wanna know, for example, if a process is spinning mindlessly. Ex: `yield()` syscall.

