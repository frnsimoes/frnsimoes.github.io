+++
date = 2025-02-02
title = "Grumpy dude's reflections on testing"
+++

I've been working in software development for almost 4 years, and although it's not an extensive amount of time, I don't think I've ever met a developer who liked to write tests. In fact, the tooling we have seems to confirm and endorse this sentiment. It's hard to write tests against services running on different nodes; it's hard to write tests against integration functionality. Mocking, faking, the London school, all these things don't bring us glory in this ungrateful field. Even worse: developers who don't write tests deliver features faster. Product owners and stakeholders are happy, and the business is happy[^1].

Despite that, one thing that doesn't leave my mind whenever I'm coding something that can be weighted in money: what if it fails? What if I'm wrong? Without tests, not only we can't be certain that we achieved the business requirements, but we don't know if there isn't some oddity in our implementation that messes with the lower level stack: how can you be sure that `http.go` implements gzip the way you are using it?

 Working with distributed systems, I came to the realization that monitoring has the same protective role as testing. It's impossible to code against multiple services without checking for logs. Otherwise, how would I know? It seems that the root cause that produces carelessness with tests is the same that produces [a house full of windows] in the monitoring world. Developers neglect meaningful logs until errors start buzzing; then we add logs everywhere, hoping that next time we’ll know what to do. 

 Logging and testing consume time. Maybe the deadline is knocking on our doors. But testing and logging are techniques that need mastering the same way coding needs mastering. It's not part of the job, it's a requirement for doing the job professionally. Mastery of them should be a part of the craft. Maybe I'm grumpy today, I don't know, but, for me, there is no reliability without ensuring that correct functionality of the higher layer of the stack.

 [^1]: Ian Cooper tells a good story in this talk: https://www.youtube.com/watch?v=EZ05e7EMOLM

 [a house full of windows]: https://ferd.ca/operable-software.html
