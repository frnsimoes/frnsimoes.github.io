+++
date = 2024-04-28
title = "What does it mean to flush a buffer?"
regular = true
+++

Flushing a buffer refers to the act of forcibly writing its contents to their destination. Buffers are temporary storage areas used to hold data before it's processed or transferred. Flushing a buffer ensures that any data waiting in the buffer is immediately written out or cleared, rather than being held in memory indefinitely. 

For example:

```
# Session 1
> touch tmp/foo
> tail -f /tmp/foo
```

```
# Session 2
> f = open('/tmp/foo', 'w')
> f.write('foo')
3
```

In this case, the operating system allows us to write "foo" into the file, but `tail` don't show it. Why? Because we need to flush the buffer before it does. 

```
# Session 2
...
f.flush()
```

```
# Session 1
...
foo
```

Why? Writing pushes up to the buffer. Flushing it puts it out.
