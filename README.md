URL Dispatcher
==============
The URL Dispatcher is an Eventlet wsgi server, that can optionally queue its requests or serve them on the fly.
Queued requests are handled by worker threads, which basically run a thread function based on the type of request.
It gets it's "URL Dispatcher" name from the fact that most of the queued request where intended to be URLs that one needs to call

It also acts as an API one can use to send SMS, by making URL calls to the API. The send SMS URL is of the following format:
http://localhost:9090/gw?username=tester&password=foobar&text=Test123&recipient=256782820208&

Installation
=============

Dependencies
============
