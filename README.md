# Dropbox Mount

In the modern day, many of us who develop run on laptops with bleeding-fast, but limited capacity SSD's.

With such limited capacity, a 20GB+ syncing Dropbox account tends to be very space-hungry, so many of us are required to either sacrifice this amount of storage, or use Dropbox only over the web interface.

There is now a better way! With Dropbox Mount, we can now mount our Dropbox's into our filesystem instead of syncing it, allowing us to get all the benefits of Dropbox without it eating up our previous SSD space.

Furthermore, this allows us to use Dropbox to augment, rather than decrement
the storage available to VPS's that we can rent on the Internet.

---

This was a hackathon project which is currently functional but not feature complete.

In particular, it is missing the following features, which will be implemented by the creator as he has time.

  0. The authentication setup flow, so that users can obtain a token from
     Dropbox to actually use the app for mounting.
  1. Better documentation for every method.
  2. Proper error handling for network down scenarios.

Please check back here every few weeks if you are interested in using this
project. This README will be updated as this project becomes more useable by
non-developer users.
