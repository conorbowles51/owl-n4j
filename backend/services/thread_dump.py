"""`kill -USR1 <worker pid>` writes every thread's Python stack to the service journal.

A worker found busy with no request in flight (2026-10-30: both workers at a full CPU each, d5b330d1's
Financial graph requests waiting five minutes before reaching the database) could not be looked into without
stopping it or attaching a debugger. The stacks go to stderr, which systemd keeps; the process carries on.
"""
import faulthandler
import signal


def install():
    if hasattr(signal, 'SIGUSR1'):
        faulthandler.register(signal.SIGUSR1, all_threads=True, chain=False)
