"""Name what holds a web worker's event loop when it stalls.

``request_speed_loop_lag`` counts each worker's stalls per minute but cannot say what caused one; a
profiler started afterwards finds a quiet worker. Here a thread beside the loop checks, every
CHECK_SECONDS, when the loop-lag probe last woke. When the loop is more than REPORT_SECONDS behind, it
logs the loop thread's stack at that moment, with the innermost application frames of the other threads
(a thread holding the interpreter shows up there), at most once every REPORT_EVERY_SECONDS per worker.

Measured on 31 Oct during a replay of Alex's session beside a test suite: 30 stalls over 1 s in 16
minutes, the longest 6.5 s, while the Financial views were recomputed. Nothing recorded what ran.

The check costs one wake every CHECK_SECONDS. LOUPE_LOOP_STALL_STACKS=0 turns it off.
"""
import logging
import os
import sys
import threading
import time
import traceback

log = logging.getLogger(__name__)

CHECK_SECONDS = 0.1
REPORT_SECONDS = 1.0
REPORT_EVERY_SECONDS = 60.0
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep
LOOP_FRAMES = 15
OTHER_THREADS = 12


class Heartbeat:
    """The loop-lag probe calls ``beat`` from the loop thread each time it wakes."""

    def __init__(self, interval=0.0):
        self.at = time.perf_counter()
        self.thread = None
        self.interval = interval  # the probe's own sleep, which is not a stall

    def beat(self):
        self.thread = threading.get_ident()
        self.at = time.perf_counter()


def _app_frames(frame):
    """Innermost first: (file relative to the backend, line, function) for frames in application code."""
    found = []
    while frame is not None:
        name = frame.f_code.co_filename
        if name.startswith(APP_ROOT) and '/site-packages/' not in name:
            found.append('%s:%d %s' % (name[len(APP_ROOT):], frame.f_lineno, frame.f_code.co_name))
        frame = frame.f_back
    return found


def describe(loop_thread, behind):
    frames = sys._current_frames()
    names = {thread.ident: thread.name for thread in threading.enumerate()}
    loop = frames.get(loop_thread)
    lines = ['Event loop at least %.1f s behind in worker %d (the full stall is in request_speed_loop_lag). Loop thread, innermost last:' % (behind, os.getpid())]
    lines += ['  ' + line.rstrip().replace('\n', '\n  ') for line in
              (traceback.format_stack(loop, limit=LOOP_FRAMES) if loop is not None else ['(not running)'])]
    others = []
    for ident, frame in frames.items():
        if ident in (loop_thread, threading.get_ident()):
            continue
        app = _app_frames(frame)
        if app:
            innermost = frame.f_code
            others.append('  %s: %s | now in %s %s' % (names.get(ident, ident), ' < '.join(app[:4]),
                          os.path.basename(innermost.co_filename), innermost.co_name))
    lines.append('Other threads in application code (%d):' % len(others))
    lines += sorted(others)[:OTHER_THREADS]
    return '\n'.join(lines)


def watch(heartbeat, stop):
    """Runs in its own thread until ``stop`` is set; one report per stall, at most one per REPORT_EVERY_SECONDS."""
    reported_beat, last_report = None, None
    while not stop.wait(CHECK_SECONDS):
        at, thread = heartbeat.at, heartbeat.thread
        behind = time.perf_counter() - at - heartbeat.interval
        if thread is None or behind < REPORT_SECONDS or reported_beat == at:
            continue
        reported_beat = at
        now = time.perf_counter()
        if last_report is not None and now - last_report < REPORT_EVERY_SECONDS:
            continue
        last_report = now
        try:
            log.warning(describe(thread, behind))
        except Exception:  # pragma: no cover - a report must never stop the watch
            log.exception('Loop stall report failed')


def start(heartbeat):
    """Start the watch for this worker; returns the event that stops it, or None when switched off."""
    if os.environ.get('LOUPE_LOOP_STALL_STACKS', '1') == '0':
        return None
    stop = threading.Event()
    threading.Thread(target=watch, args=(heartbeat, stop), name='loop-stall-watch', daemon=True).start()
    return stop
