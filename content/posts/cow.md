+++
date = 2025-11-22
title = "What happens when copy-on-write?"
aliases = ["/gcb/cow/"]
+++ 

Today I took some time to actually find out what was happening to one of our containers. Zenduty kept buzzing me that a certain app was failing because of memory issues. The log:

> WARNING Memory overcommit must be enabled! Without it, a background save or replication may fail under low memory condition.

Fine. Let's figure out what this actually means.

Redis [documentation](https://redis.io/docs/latest/develop/get-started/faq/#background-saving-fails-with-a-fork-error-on-linux) is pretty clear about this issue. Here is the important part: the kernel can't predict how many pages will be written during the child's lifetime. In the worst case, all pages might need copying, so it needs to ensure enough memory exists for full duplication. 

While reading the documentation, I made some (slightly bad) assumptions, because I thought that I knew what was going on. I didn't:

- This is similar to Postgres full vacuum: it copies things. The only difference is that Postgres copies bytes on disk and Redis on memory.
- Fork gives the child a copy of the parent's address space

I was in the right direction, but missing the mechanism. 

## How does forking/cloning affect virtual memory?

When forking/cloning, the kernel says: hey, kid, before you exec, you can share the same physical pages in memory as your parent. I won't give you a full virtual memory yet. 

It's something like this:

```
Parent virtual addr -> [MMU uses Parent's page table] -> physical page X
Child virtual addr  -> [MMU uses Child's page table]  -> physical page X (same!)
```

When the child is created, it can do a few different things. One of them, that's really interesting to our case, is when the child tries to write to that shared virtual memory. Imagine this:

```
int main() {
    char *data = malloc(4096);
    memset(data, 'A', 4096);
    
    pid_t pid = fork();
    
    if (pid == 0) {
        data[0] = 'B';  // child writes
        exit();
    
    } else { // parent's 
        ... data[0];
    }
}
```

`data` is allocated to the heap of the parent's process, then the child tries to write to it. What should the kernel do?

Let's think this through:

If `data` was `ALLOW`, and then the child replaces `A` with `B`, the parent's process will fetch this value from memory and get `BLLOW`. From the top of my head, I can see three possible ways of dealing with this:

- `BLLOW` is now the value of data (parent sees child's writes).
- The kernel says "nope, kiddo" to the child's attempt at writing and terminates the child process.
- The kernel handles it behind the scenes so both processes have their own copies.

Hopefully you'll agree that the last one is what we want.

This mechanism is called copy-on-write. When the child tries to write to a shared page, the kernel allocates a new physical page, copies the content, and updates the child's page table to point to the new page. The write happens there, isolated from the parent.

What happens is something like this:

```
Initially:
Parent virtual addr -> [MMU uses Parent's page table] -> physical page X (ALLOW)
Child virtual addr  -> [MMU uses Child's page table]  -> physical page X (ALLOW)

After child writes:
Parent virtual addr -> [MMU uses Parent's page table] -> physical page X (ALLOW)
Child virtual addr  -> [MMU uses Child's page table]  -> physical page Y (BLLOW)
```

The kernel has a few functions and structures that handle these cases. Let's explore them.

## When the kernel actually handles this

The function that handles copy-on-write is `__handle_mm_fault` (mm/memory.c). Here's the important part:

```
if (vmf->flags & (FAULT_FLAG_WRITE|FAULT_FLAG_UNSHARE)) {
    if (!pte_write(entry))
        return do_wp_page(vmf);
    else if (likely(vmf->flags & FAULT_FLAG_WRITE))
        entry = pte_mkdirty(entry);
}
```

How does it work? `vmf` is a [struct](https://lwn.net/Articles/242625/), `vm_fault`. The kernel is checking if this virtual memory fault has one of these two flags: FAULT_FLAG_WRITE or FAULT_FLAG_UNSHARE.

The first one is what we're looking for: it "indicates that the page fault happened on a write access". In `do_wp_page`, the kernel handles shared memory, private memory, etc. The kernel delays copying until absolutely necessary because it's expensive - why duplicate a page if it might never be written to?

After all checks and validations, it finally grants:

```
/*
 * Ok, we need to copy. Oh, well..
 */
if (folio)
    folio_get(folio);
    pte_unmap_unlock(vmf->pte, vmf->ptl);

#ifdef CONFIG_KSM
	if (folio && folio_test_ksm(folio))
		count_vm_event(COW_KSM);
#endif
	return wp_page_copy(vmf);
}
```

It finally calls `wp_page_copy` (mm/memory.c), receiving the virtual memory fault struct. This function does multiple things. Let's check out a few of them:

- It tries to allocate a new memory page. OOM if it fails.

```
new_folio = folio_prealloc(mm, vma, vmf->address, pfn_is_zero);
if (!new_folio)
    goto oom;
```

- Copies the content of old page to the new one. (Here's the problem for Redis)

```
err = __wp_page_copy_user(&new_folio->page, vmf->page, vmf);
```

- Marks the page table as writable (maybe_mkwrite; should be writable, but depends on other things)

```
entry = folio_mk_pte(new_folio, vma->vm_page_prot);
entry = maybe_mkwrite(pte_mkdirty(entry), vma);
```

- Cleans old TLB entry

```
ptep_clear_flush(vma, vmf->address, vmf->pte);
```

- Adds new TLB entry

```
set_pte_at(mm, vmf->address, vmf->pte, entry);
```

But what does this have to do with Redis, overcommit, etc? Actually, what's even overcommit?

## Why this breaks Redis

Redis's background saving ([BGSAVE/RDB](https://redis.io/docs/latest/commands/bgsave/) persistence) forks a child process. This child walks through Redis's entire dataset to write it to disk. During this walk, the child reads from memory pages shared with the parent.

Meanwhile, the parent keeps serving requests. When clients write to Redis, the parent modifies pages. Each modified page triggers copy-on-write - the kernel allocates a new physical page, copies the old content, and updates the child's page table to point to the new copy.

Worst case? Every page gets written during the save. If Redis is using 3GB, the kernel might need to allocate another 3GB for all those COW copies.

But here's the problem: the kernel can't know in advance which pages will be written. It only knows the theoretical maximum - the full dataset size.

Redis documentation recommends `vm.overcommit_memory=1`. This basically means: always say yes to memory allocations, even if there's not enough RAM to back them all.

Is it safe? Will it break everything? If we think about it, Redis won't probably write to *every* page during the background save, right? It will probably write to a *few* pages. And considering a page is 4kb, it's safe enough in practice. The kernel will only allocate what's actually needed through COW, not the theoretical maximum.

## Why is this a problem

I finally understood Andrew Baumann takes about the fork/exec model in the [a fork() in the road](https://www.microsoft.com/en-us/research/wp-content/uploads/2019/04/fork-hotos19.pdf) paper. Requiring overcommit is a problem, no one can deny. Even if the chances are too low, they still exist, and applications can simply fail because of this. This is the perfect example of the `worst-case allocation` Baumman mentions. 

Copy-on-write exists to avoid wasteful page copies. The "* Ok, we need to copy. Oh, well..." commentary in memory.c is quite revealing. But overcommiting memory is like the Kernel is saying: "I can compromise resources I don't have because I don't know what to do with this". 

