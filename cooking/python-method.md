+++
date = 2023-04-26
title = "What happens when you call a method in Python"
tags = ["programming languages"]
+++

```
class C:
    def sum_numbers(self, x, y):
        return x + y
```

Who is `sum_numbers`? There is a difference in answers depending on who I ask.

If I ask `class C` if it knows `sum_numbers`, this is what it tells me:

```
>>> C.sum_numbers
<function C.sum_numbers at 0x1031964d0>
```

But if I ask the same question to C's instance, here is what I get in return:

```
>>> c = C()
>>> c.sum_numbers
<bound method C.sum_numbers of <t.C object at 0x102fffc70>>
```

This means that the instance doesn't know `sum_numbers`. It only knows that `sum_numbers` is somewhere in the tree of the objects that it is an instance of.

Let's give `c.sum_numbers` a referenceable local in the memory, and ask it who it thinks it is:

```
m = c.sum_numbers
m.__self__
m.__func__
<t.C object at 0x1030ba2c0>
<function C.sum_numbers at 0x1031964d0>
```

This clarifies what the Python documentation means [here](https://docs.python.org/3/reference/datamodel.html):

> When an instance method object is created by retrieving a user-defined function object from a class via one of its instances, its __self__ attribute is the instance, and the method object is said to be bound. The new method’s __func__ attribute is the original function object.

> When an instance method object is created by retrieving a class method object from a class or instance, its __self__ attribute is the class itself, and its __func__ attribute is the function object underlying the class method.

> When an instance method object is called, the underlying function (__func__) is called, inserting the class instance (__self__) in front of the argument list. For instance, when C is a class which contains a definition for a function f(), and x is an instance of C, calling x.f(1) is equivalent to calling C.f(x, 1).

To summarize, Python's method call knows two really important things: a. its `__self__` is a reference to the instance, b. its `__func__` is a reference to the class function.

Under the hoods, `instance.method(x, y)` is the method doing its magic with what it knows about itself: `m.__func__(m.__self__, 40, 2)`

A full example of this dramatic and healing self-discovered journey:

```
# Attributions
m = C().sum_numbers
>>> m.__self__

<t.C object at 0x103192680>
>>> # The method __func__ is not the instance method, but the class function

>>> m.__func__
<function C.sum_numbers at 0x1031964d0>

# Into the depths
>>> m(40, 2)
42

>>> m.__call__(40, 2)
42

>>> m.__func__(m.__self__, 40, 2)
42
```

By calling `__func__` we need to reference `self` (`m.__self__`). But when we use `__call__`, the `self` is magically attributed to the func. This means that `m.__call__` is the same as `m.__func__(m.__self__)`.

At the end of this dramatic and beautiful self-discovering journey, a call of a Python class method is represented like this:

```
>>> m.__func__(m.__self__, 40, 2)
42
```
