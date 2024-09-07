+++ 
date = 2024-09-05
title = "Big bye bye to Apple"
+++

Oh dang, Apple ruined it all. I remember when I bought my first MacBook Air back in 2015. I had a Dell laptop before that, and the difference was... hmm. Since then, I've been using macOS. The productivity boost was insane, and I still had the Unix shell on hand. I used to write legal petitions with Markdown in the terminal. But as the years went by, the hope, the enthusiasm, the waiting, all ended. Every year I got less and less excited about the new version of the OS. Then, recently, Apple announced OpenAI integration with the operating system. That's a big no-no. No OpenAI integration on my machine.

So I bought a cheap ThinkPad (less than half the price of a new MacBook Air M3) to build a Linux machine. In one week, I guess I achieved something useful—something nice, smooth, and beautiful (I didn’t even like macOS UI). Debian. I'm old. Debian is good for old people—or so they say. I want stability and security. First I tried Gnome, then KDE, then Fluxbox, then i3. But XFCE4 was the sweet spot for me: light, beautiful, customizable. So there it was: Debian and XFCE.

I wrote some shell scripts to handle workflows, things I used to do with Alfred or the UI on macOS: managing audio, muting Spotify, changing monitor resolution, copying my social security number, phone number, and little utilities like that. Shell scripts can do anything, and it feels good to be getting better at it. One thing I miss is opening Alfred’s UI and searching for anything on my machine by name—whether it's a directory, a file, anything. Now I use find.

I've been using terminals to write text since at least 2020, so I don’t miss any text-writing software (I used to love Ulysses back in the day). Since my coding workflow lives in the terminal, I don’t miss anything else, to be honest. XFCE is way faster and nicer than macOS UI. I can switch between workspaces at the speed of thought.

Things I still don’t like: there’s still that sense of "dread" when I see the bloated top output. I felt the same way with macOS, but now that I use Linux, I’ve been wanting more and more control over the processes running. I don’t like feeling like my machine is something I don’t fully understand.

Things I learned that are really cool:

- If I open, say, Firefox from the terminal, the terminal is the parent process, and Firefox is the child. An execve is running behind the scenes, which blocks stdout. Never thought about that before.
- I never thought that audio, power, or screen management was something a DE or WM would be responsible for. Those are crucial things, right? But yes, I was amazed to discover that on i3, closing my laptop lid wouldn’t automatically make the screen appear on my monitor. DEs like XFCE interface with system-level services. That was a cool discovery.
- File systems! Discovering chroot on a Saturday afternoon was like finding one more beer in the fridge when you thought there was none left.
- I don’t want to mess with Bluetooth anymore.

Things I want to do:

- I don´t know if I like the Markdown setup I built. Little pieces all over the place. Maybe something more... elegant, simple?
- More control over the machine? How?
- Becoming a shell script magician. 
