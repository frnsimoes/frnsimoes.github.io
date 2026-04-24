+++
date = 2026-04-15
title = "The cost of not measuring"
labels = ["hide"]
+++

Probability theory has a precise model for what happens when you act without measuring: the multi-armed bandit problem.

You're in a casino with k slot machines, each paying out at a different rate, and n rounds to play. The question is how you split those rounds between *finding out* and *cashing in*.

The dumbest viable strategy is called [Explore-Then-Commit](https://en.wikipedia.org/wiki/Explore-then-commit_algorithm): try each machine m times, average the payouts, then go with the winner. It works, but it's not optimal. Measurement isn't free. Too few rounds *exploring*, and you commit with bad data. But if you explore too much, you burn rounds you could have spent on the best machine.

Now look at the degenerate case of ETC: **m = 0**. You walk in, you like the blue slot machine, so you decide to pull the blue machine forever. Every round you might be on the wrong machine, but you will never know because you have no way to tell that's the case. Your regret grows linearly with time, which is the formal way of saying you bleed value on every single pull and die ignorant.

Try it:

{{< bandit >}}

Run it a few times. m = 0 doesn't always lose - sometimes instinct picks the right machine and you look like a genius over 100 rounds. Instinct can be right, sometimes, the problem is you have no way to find out when it isn't, and regrets accumulates invisibly. Measurement, on the other hand, doesn't guarantee you're right, but it guarantees you can be shown wrong.

ETC treats measurement as a phase to get through. In the [Upper Confidence Bound](https://en.wikipedia.org/wiki/Upper_Confidence_Bound)  algorithm, you never fully stop exploring. But you explore less as confidence grows. The difference is that the cost gets logarithmic instead of linear. And because UCB has to keep betting on uncertain arms, exploration means taking risks.

Try it:

{{< bandit-ucb >}}

UCB works because there's a *bonus* for exploring the less known options. The bonus is knowledge.

A team that measures can still be wrong. But at least in this case they are wrong about something real.

