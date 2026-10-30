"""`kill -USR1 <worker pid>` writes every thread's Python stack to a file: what a busy worker is doing.

A worker found busy with no request in flight (2026-10-30: both workers at a full CPU each, d5b330d1's
Financial graph requests waiting five minutes before reaching the database) could not be looked into without
stopping it or attaching a debugger. The process carries on. The stacks go to
``$LOUPE_THREAD_DUMP_DIR/threads-<pid>.txt`` (default /tmp/loupe-thread-dumps), replaced at each signal: written
to the journal, two workers' dumps arrived in fragments interleaved with each other and could not be read.

The stacks are read in a Python signal handler (main thread, holding the interpreter lock: sys._current_frames),
not by faulthandler. faulthandler walks other threads' frames from the C signal handler while they run, which
Python documents as unsafe: live 2026-10-30 15:36 a batch rounds process ended with SIGSEGV half-way through such
a dump. The cost: the dump waits until the main thread next runs Python code (an event loop wakes for it).
"""
import os
import signal
import sys
import threading
import traceback


def dump_path(pid=None):
    directory = os.environ.get('LOUPE_THREAD_DUMP_DIR', '/tmp/loupe-thread-dumps')
    return os.path.join(directory, f'threads-{pid or os.getpid()}.txt')


def format_threads():
    """Every thread's stack, most recent call first (as faulthandler printed it)."""
    names = {thread.ident: thread.name for thread in threading.enumerate()}
    current = threading.get_ident()
    blocks = []
    for ident, frame in sys._current_frames().items():
        head = ('Current thread' if ident == current else 'Thread') + f' 0x{ident:016x} ({names.get(ident, "?")}, most recent call first):'
        lines = [f'  File "{entry.filename}", line {entry.lineno} in {entry.name}'
                 for entry in reversed(traceback.extract_stack(frame))]
        blocks.append('\n'.join([head] + lines))
    return '\n\n'.join(blocks) + '\n\n'


def write_dump(path=None):
    """Append every thread's stack to this process's file (stderr only if the file cannot be written)."""
    path = path or dump_path()
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        with open(path, 'a') as dump:
            dump.write(format_threads())
    except OSError:
        sys.stderr.write(format_threads())


def install():
    if not hasattr(signal, 'SIGUSR1') or threading.current_thread() is not threading.main_thread():
        return
    path = dump_path()
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        open(path, 'w').close()
    except OSError:
        pass
    signal.signal(signal.SIGUSR1, lambda signum, frame: write_dump(path))
