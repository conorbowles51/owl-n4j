"""Bounded process shutdown.

A stop has three phases, and each used to be able to wait forever:

1. Uvicorn waits for in-flight request tasks ("Waiting for background tasks to
   complete"). Without ``--timeout-graceful-shutdown`` it never gives up, and a
   second SIGTERM does not force it; only SIGINT does.
2. The lifespan cancelled its background loops and then awaited them. A loop
   inside an atomic statement unit or the identity-graph sweep awaits a worker
   thread, and a thread cannot be cancelled.
3. Anything that blocks the event loop itself stops both of the above.

This module bounds all three:

- ``install_signal_handlers`` chains onto Uvicorn's SIGTERM/SIGINT handlers.
  The first signal sets ``requested`` (loops observe it and stop starting new
  units of work) and arms a watchdog thread.
- ``stop_background_tasks`` cancels the lifespan's tasks and waits for them for
  a bounded time. A task still running after that is abandoned: the process
  exits around it. Every abandoned unit is durable work (a leased import batch,
  a pending recovery item, a revisioned graph sweep) that the next start
  resumes; its open database transaction rolls back when the process ends.
- The watchdog ends the process after a hard deadline if it is still alive,
  whatever is holding it. Before that it logs what was still running, so the
  next hung stop names its culprit instead of only "Waiting for background
  tasks".

Request tasks are bounded by Uvicorn's own ``timeout_graceful_shutdown``,
configured on the service (see ``deploy/ingestion-safety.sh``). The watchdog is
the backstop when that setting is absent.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import threading
import time
from typing import Callable, Iterable, Optional


def _seconds(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


# Lifespan wait for its own background loops after cancelling them.
BACKGROUND_STOP_SECONDS = _seconds("LOUPE_SHUTDOWN_BACKGROUND_SECONDS", 10.0)
# Hard deadline from the first stop signal to process exit.
HARD_DEADLINE_SECONDS = _seconds("LOUPE_SHUTDOWN_DEADLINE_SECONDS", 45.0)
# When the watchdog reports still-running asyncio tasks (before the deadline).
DIAGNOSE_AFTER_SECONDS = _seconds("LOUPE_SHUTDOWN_DIAGNOSE_SECONDS", 25.0)

requested = threading.Event()

_lock = threading.Lock()
_watchdog: Optional[threading.Thread] = None
_loop: Optional[asyncio.AbstractEventLoop] = None


def shutdown_requested() -> bool:
    """True once the process has been asked to stop."""
    return requested.is_set()


def _say(message: str) -> None:
    # Written directly: the watchdog may end the process immediately after,
    # and no logging configuration is guaranteed under Uvicorn workers.
    try:
        sys.stderr.write(f"[shutdown] {message}\n")
        sys.stderr.flush()
    except Exception:
        pass


def describe_task(task: asyncio.Task) -> str:
    """Name a task by the innermost coroutine it is suspended in.

    For a Uvicorn request task the ASGI path is included, which is what
    identifies a hung request.
    """
    parts = [task.get_name()]
    try:
        coro = task.get_coro()
        frame = getattr(coro, "cr_frame", None)
        owner = frame.f_locals.get("self") if frame is not None else None
        scope = getattr(owner, "scope", None)
        if isinstance(scope, dict) and scope.get("path"):
            parts.append(f"{scope.get('method', scope.get('type', ''))} {scope['path']}".strip())
        innermost = coro
        for _ in range(64):
            nxt = getattr(innermost, "cr_await", None) or getattr(innermost, "gi_yieldfrom", None)
            if nxt is None or not (hasattr(nxt, "cr_frame") or hasattr(nxt, "gi_frame")):
                break
            innermost = nxt
        inner_frame = getattr(innermost, "cr_frame", None) or getattr(innermost, "gi_frame", None)
        if inner_frame is not None:
            code = inner_frame.f_code
            parts.append(f"at {code.co_qualname} ({os.path.basename(code.co_filename)}:{inner_frame.f_lineno})")
    except Exception:
        pass
    return " ".join(parts)


def _log_pending_tasks() -> None:
    try:
        current = asyncio.current_task()
        tasks = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
    except Exception:
        return
    _say(f"{len(tasks)} asyncio task(s) still running:")
    for task in tasks:
        _say(f"  {describe_task(task)}")


def _log_threads() -> None:
    frames = sys._current_frames()
    me = threading.get_ident()
    for thread in threading.enumerate():
        if thread.ident in (None, me):
            continue
        frame = frames.get(thread.ident)
        where = ""
        if frame is not None:
            where = f" at {frame.f_code.co_qualname} ({os.path.basename(frame.f_code.co_filename)}:{frame.f_lineno})"
        _say(f"  thread {thread.name!r} daemon={thread.daemon}{where}")


def _watch(deadline: float, diagnose_after: float, loop, exit_process: Callable[[int], None]) -> None:
    started = time.monotonic()
    if loop is not None and diagnose_after < deadline:
        time.sleep(diagnose_after)
        try:
            loop.call_soon_threadsafe(_log_pending_tasks)
        except RuntimeError:
            pass  # Loop already closed: nothing left to report.
    remaining = deadline - (time.monotonic() - started)
    if remaining > 0:
        time.sleep(remaining)
    _say(f"Stop did not finish within {deadline:g}s of the first stop signal; ending the process. "
         "Durable work resumes on the next start. Threads still running:")
    _log_threads()
    exit_process(1)


def request_shutdown(*, deadline: Optional[float] = None, diagnose_after: Optional[float] = None,
                     exit_process: Callable[[int], None] = os._exit) -> None:
    """Mark the process as stopping and arm the hard-deadline watchdog once."""
    global _watchdog
    requested.set()
    with _lock:
        if _watchdog is not None:
            return
        deadline = HARD_DEADLINE_SECONDS if deadline is None else deadline
        diagnose_after = DIAGNOSE_AFTER_SECONDS if diagnose_after is None else diagnose_after
        _watchdog = threading.Thread(
            target=_watch, args=(deadline, diagnose_after, _loop, exit_process),
            name="loupe-shutdown-watchdog", daemon=True)
        _watchdog.start()


def install_signal_handlers(*, exit_process: Callable[[int], None] = os._exit) -> bool:
    """Chain onto the current SIGTERM/SIGINT handlers (Uvicorn's).

    Call from the lifespan startup, which runs on the main thread inside
    Uvicorn's signal capture. Uvicorn restores its own saved handlers when it
    stops serving, so nothing installed here outlives the server. Returns False
    when not on the main thread (e.g. a test client), where signals cannot be
    handled.
    """
    global _loop
    if threading.current_thread() is not threading.main_thread():
        return False
    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        _loop = None
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous = signal.getsignal(sig)

        def handler(signum, frame, previous=previous):
            request_shutdown(exit_process=exit_process)
            if callable(previous):
                previous(signum, frame)
            elif previous == signal.SIG_DFL:
                signal.signal(signum, signal.SIG_DFL)
                os.kill(os.getpid(), signum)

        signal.signal(sig, handler)
    return True


async def stop_background_tasks(tasks: Iterable[Optional[asyncio.Task]],
                                timeout: Optional[float] = None) -> set:
    """Cancel the lifespan's background tasks and wait a bounded time.

    Returns the tasks still running when the bound expired. They are
    abandoned, not awaited: the caller proceeds to close clients and the
    process exits. Their durable records resume on the next start.
    """
    requested.set()
    live = [task for task in tasks if task is not None]
    for task in live:
        task.cancel()
    if not live:
        return set()
    timeout = BACKGROUND_STOP_SECONDS if timeout is None else timeout
    done, pending = await asyncio.wait(live, timeout=timeout)
    for task in done:
        if not task.cancelled() and task.exception() is not None:
            _say(f"Background task {task.get_name()} ended with {type(task.exception()).__name__} during shutdown")
    if pending:
        _say(f"{len(pending)} background task(s) did not stop within {timeout:g}s and are abandoned; "
             "their durable work resumes on the next start:")
        for task in pending:
            _say(f"  {describe_task(task)}")
    return pending


def _reset_for_tests() -> None:
    global _watchdog, _loop
    requested.clear()
    with _lock:
        _watchdog = None
    _loop = None
