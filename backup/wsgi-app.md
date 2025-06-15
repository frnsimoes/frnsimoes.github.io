+++ 
date = 2023-12-30
title = "I wrote a WSGI application"
regular = true
+++
This Christmas, I decided to create a really simple server framework in Python, implementing a WSGI application.

I was mostly interested in learning more about how different frameworks in Python handle design choices in implementation, especially regarding the abstractions of requests and responses.

I had the chance to explore Flask (and Werkzeug), Bottle, Django, and some details of HTTP messages. There is still much more to learn, though!

I started by trying to deal with the intricate details of sockets, but I gave up soon enough to concentrate on the WSGI application itself.

It was a fun journey, and I certainly intend to come back to enhance it. I’m also really curious about how sockets are implemented behind the scenes (by, say, Gunicorn)

Check it out [here](https://github.com/frnsimoes/simple-http) :).
