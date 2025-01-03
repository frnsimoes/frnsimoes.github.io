+++ 
date = 2022-06-10
title = "Invariants"
description = "Exploring invariants"
tags = ["Programming", "Python", "Domain-driven design"]
+++


A rule in Domain-Driven Design (DDD) states that "each entity should self-validate." This rule is clear, simple, and functional when we think of an entity like Person, where the name attribute cannot be an empty string. It would be strange and absurd to consider that the validation of name should occur outside the Person entity, either during instance creation or when calling the method. There are various ways to perform internal validation, and this article provides an interesting perspective on them.

However, outside the realm of object-oriented programming, it's easy to lose the sense of an object's "unity."

"Paying a subscription" is a set of business rules represented by small functions that call each other, and even for the programmer writing them, there seems to be no unity between them. At least not unity in the sense of an "entity." The unity is in the domain, and often the domain is spread across various different places.

Programmers always face a choice. Consider the example:

```
# Option 1

## Module A
def create_checkout_subscription(...) -> None:
    create_subscription(...)

## Module B
if payment.status == 'PAID':
    create_checkout_subscription

# Option 2

# Module A
def create_checkout_subscription(...) -> None:
    if payment.status == 'PAID':
        create_subscription(...)
 
# Module B
do_something(...)
create_checkout_subscription(...)
do_one_more_thing(...)
```
Faced with these two options, it's easy to intuitively conclude that the second one is better. With it, we don't need to validate the create_checkout_subscription function everywhere it's called. But intuition is not enough.

What if the scenario were like this?:

```
# Module A
def create_checkout_subscription(payment: Payment) -> None:
    if payment.status == 'PAID':
        create_subscription(...)
        
# Module B
if payment.status == 'PAID':
    send_email.enqueue(...)
    # create_checkout_subscription()
```
In this case, external validation would be enforced by another function: send_email, whose internal constraints do not mandate that an email will only be sent if the status is 'PAID' in all cases (the function is called in various other parts of the system without incurring this contextual restriction).

If the programmer first encounters this scenario where the business restriction was established externally (in this case, in Module B), they may end up convincing themselves that when creating the create_checkout_subscription function, they don't need to create any internal restrictions.

Researching this issue that was bothering me—after all, how terrible is it to program based on feeling 100% of the time without being able to name things?—I bothered friends and looked into the subject.

I found some answers:

[This response from Uncle Bob](https://groups.google.com/g/clean-code-discussion/c/latn4x6Zo7w/m/bFwtDI1XSA8J?pli=1). The topic is clean architecture, and the context is entities, but the idea is already getting clearer:
Should the age restriction be enforced by the employee entity, or by a sub-interactor called by the add-employee-interactor and the change-employee-interactor? This depends entirely on the volatility of the policy.
(The notion of "volatility": if things can change, and we know they can, an external restriction to the entity is a better option. Otherwise, the internally established restriction is better.)

[This answer on Stack Overflow](https://stackoverflow.com/questions/30190302/what-is-the-difference-between-invariants-and-validation-rules). The context is a question about invariant rules and validations:
Absolutely, validation is the process of approving a given object state, while invariant enforcement happens before that state has even been reached.
(Perfect! It becomes easy to understand that, within a specific context, an invariant is an external limitation of the entity.)
