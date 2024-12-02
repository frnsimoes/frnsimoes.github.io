+++
date = 2024-12-02
title = "Testing software"
+++

I've been working in software development for almost 4 years, and although it's not an extensive amount of time, I don't think I've ever met a developer who liked to write tests. In fact, the tooling we have seems to confirm and endorse this sentiment. It's hard to write tests against services running on different nodes; it's hard to write tests against integration functionality. Mocking, faking, the London school, all these things don't bring us glory in this ungrateful field. Even worse: developers who don't write tests deliver features faster. Product owners and stakeholders are happy, and the business is happy[^1].

I'm the type of person who rarely advocates for one thing or another *in abstracto*. Things tend to behave differently in different contexts. But testing is an exception. I remember when I started coding, and all I wanted was a way to see what was happening. I didn’t know about tests at the time. When I started at my first job, working on a Django monolith, I simply couldn't code if there was no way for me to confirm that I wrote the desired outcome. I wrote tests for everything.

For this reason, I simply cannot understand how someone can code out of thin air, trusting that they are doing the right thing. Without tests, not only we can't be certain that we achieved the business requirements, but we don't know if there isn't some oddity in our implementation that messes with the lower level stack: how can you be sure that `http.go` implements gzip the way you are using it?

Maybe I'm a little obsessed: there's one thing that Ian Cooper says that I don't seem to agree with: the advice is "test against behavior, not implementation". I get it. Testing against behavior requires a higher level of code quality, and testing becomes easier. I get the whole code-quality thing that everyone loves, including me. But, how can you be sure? Suppose we have a simple function that is caching a very simple select and returning data from the database. The implementation is coupled with behavior. Another example is when the codebase is a mess, and code quality isn’t shining. Not testing things because it's too messy forces us to live in the Postman UI.  

 Working with distributed systems, I came to the realization that monitoring has the same protective role as testing. It's impossible to code against multiple services without checking for logs. Otherwise, how would I know? It seems that the root cause that produces carelessness with tests is the same that produces [a house full of windows] in the monitoring world. Developers neglect meaningful logs until errors start buzzing; then we add logs everywhere, hoping that next time we’ll know what to do.. 

 Logging and testing consume time. Maybe the deadline is knocking on our doors. But testing and logging are techniques that need mastering the same way coding needs mastering. It's not part of the job, it's a requirement for doing the job professionally. Mastery of them should be a part of the craft. Maybe I'm grumpy today, I don't know, but, for me, there is no reliability without ensuring that correct functionality of the higher layer of the stack.

 [^1]: Ian Cooper tells a good story in this talk: https://www.youtube.com/watch?v=EZ05e7EMOLM

 [a house full of windows]: https://ferd.ca/operable-software.html
