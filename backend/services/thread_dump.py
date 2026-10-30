"""`kill -USR1 <worker pid>` writes every thread's Python stack to a file: what a busy worker is doing.

A worker found busy with no request in flight (2026-10-30: both workers at a full CPU each, d5b330d1's
Financial graph requests waiting five minutes before reaching the database) could not be looked into without
stopping it or attaching a debugger. The process carries on. The stacks go to
``$LOUPE_THREAD_DUMP_DIR/threads-<pid>.txt`` (default /tmp/loupe-thread-dumps), replaced at each signal: written
to the journal, two workers' dumps arrived in fragments interleaved with each other and could not be read.
"""
import faulthandler
import os
import signal

_files = []


def dump_path(pid=None):
    directory = os.environ.get('LOUPE_THREAD_DUMP_DIR', '/tmp/loupe-thread-dumps')
    return os.path.join(directory, f'threads-{pid or os.getpid()}.txt')


def install():
    if not hasattr(signal, 'SIGUSR1'):
        return
    path = dump_path()
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        dump = open(path, 'w')
    except OSError:
        faulthandler.register(signal.SIGUSR1, all_threads=True, chain=False)  # stderr, as a last resort
        return
    _files.append(dump)  # kept open for the process's life: faulthandler writes to its descriptor
    faulthandler.register(signal.SIGUSR1, file=dump, all_threads=True, chain=False)
