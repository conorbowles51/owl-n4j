"""Financial views computed again in the background after a write, so a person never waits for it.

When the rows a slow kept view was computed from change, a request from the Financial page is answered with the
previous copy marked updating (view_cache._serve_previous) and asks here for the view to be computed again. An ask
is one small file in the memo directory (``refresh-wanted``), so both workers and every later request see it. Each
worker checks for asks every POLL_SECONDS from its event loop; when there are any and no refresh is running on the
host, it starts one child process (this module, ranked below the request threads, ended with the worker). The
child computes each asked view through its own route handler and the view cache, exactly as a request without the
updating mark would, saves it (however fast), and removes the ask. The next request finds the saved copy current.

An ask the child could not complete (the view failed, or its parameters no longer give the same key) is marked
failed and left: once it is older than view_cache.UPDATING_MAX_SECONDS the request computes the view itself and
shows its own answer or error. Asks made by other code (a release in between) are left to that code's processes.
FINANCIAL_VIEW_UPDATING=0 turns the updating answers, and so the asks, off.
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import os
import threading
import time

from services.financial.journal import journal

logger = journal(__name__)

WANTED_DIR = 'refresh-wanted'
LOCK = 'refresh.lock'
POLL_SECONDS = 1.0
# The child stays this long after its last ask: corrections arrive in bursts (16 in 3 min, measured 2026-10-31).
IDLE_EXIT_SECONDS = 120
CHILD_FLAG = '--refresh-child'
# Route modules whose cached views can be asked for (importing them registers their handlers).
ROUTE_MODULES = ('routers.financial_ledger', 'routers.financial_statement_import', 'routers.evidence', 'routers.financial')


def _wanted_dir():
    from services.financial import view_cache
    directory = view_cache._memo_dir()
    return None if directory is None else directory / WANTED_DIR


def _path(directory, key):
    return directory / (hashlib.sha256(json.dumps(list(key)).encode()).hexdigest() + '.json')


def _read(path):
    try:
        ask = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return ask if isinstance(ask, dict) and isinstance(ask.get('asked'), (int, float)) else None


def _write(path, ask):
    temporary = path.with_name('%s.%d.%d.tmp' % (path.name, os.getpid(), threading.get_ident()))
    temporary.write_text(json.dumps(ask, sort_keys=True))
    os.replace(temporary, path)


def ask(key, case_id):
    """Ask for this view to be computed again. Returns when the outstanding ask for it was first made (epoch
    seconds), or None when asks cannot be kept (no memo directory or code identity)."""
    from services.financial import view_cache
    directory, code = _wanted_dir(), view_cache.code_identity()
    if directory is None or code is None:
        return None
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = _path(directory, key)
    current = _read(path)
    if current is not None and current.get('code') == code and current.get('key') == list(key):
        return current['asked']
    asked = time.time()
    _write(path, dict(key=list(key), case_id=str(case_id), asked=asked, code=code))
    return asked


def forget(key):
    """Remove the ask for this view (its request computes it itself)."""
    directory = _wanted_dir()
    if directory is not None:
        try:
            _path(directory, key).unlink()
        except FileNotFoundError:
            pass


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# Asks of other code (a release in between) are removed after this long; no process of that code is left by then.
OTHER_CODE_SECONDS = 3600


def _open_asks(code):
    """(path, ask) of this code's asks not marked failed, oldest first. An ask whose refresh process ended without
    finishing it (killed, out of memory) is marked failed, so no new process takes it first again."""
    directory = _wanted_dir()
    if directory is None:
        return []
    try:
        names = [entry.name for entry in os.scandir(directory) if entry.name.endswith('.json')]
    except FileNotFoundError:
        return []
    asks = []
    for name in names:
        path = directory / name
        ask_ = _read(path)
        if ask_ is None:
            continue
        if ask_.get('code') != code:
            if time.time() - ask_['asked'] > OTHER_CODE_SECONDS:
                path.unlink(missing_ok=True)
            continue
        if ask_.get('failed'):
            continue
        started = ask_.get('started')
        if isinstance(started, dict) and started.get('pid') != os.getpid() and not _alive(started.get('pid') or 0):
            _write(path, {**ask_, 'failed': time.time()})
            logger.warning('Financial view %s refresh ended unfinished (process %s); left to its request',
                           ask_['key'][0], started.get('pid'))
            continue
        asks.append((path, ask_))
    return sorted(asks, key=lambda pair: pair[1]['asked'])


def _typed(handler, parameters):
    """The route handler's keyword arguments from a kept key's parameters (strings), by its annotations."""
    import inspect
    import typing
    from pydantic import TypeAdapter
    signature = inspect.signature(handler)
    arguments = {}
    for name, value in parameters.items():
        annotation = signature.parameters[name].annotation
        if annotation is inspect.Parameter.empty:
            arguments[name] = value  # kept as the string it was keyed by
            continue
        if typing.get_origin(annotation) is typing.Annotated:
            annotation = typing.get_args(annotation)[0]
        arguments[name] = None if value is None else TypeAdapter(annotation).validate_python(value)
    return arguments


def refresh_one(path, ask_, session_factory=None):
    """Compute one asked view through its route; True only when a current copy was saved where the workers read
    it (written now, or already saved and current): a copy kept only in this process's memory is no refresh."""
    import importlib
    from services.financial import view_cache
    for module in ROUTE_MODULES:
        importlib.import_module(module)
    name, parameters = ask_['key'][0], json.loads(ask_['key'][1])
    visit_token = view_cache.not_a_visit.set(True)
    try:
        return _refresh_one(name, parameters, ask_, session_factory)
    finally:
        view_cache.not_a_visit.reset(visit_token)


def _refresh_one(name, parameters, ask_, session_factory):
    from fastapi import HTTPException
    from services.financial import view_cache
    from postgres.session import _get_session_local
    if name == 'review-queue':
        from uuid import UUID
        from services.financial import review_queue
        view_cache.clear()
        token = view_cache.always_save.set(True)
        try:
            with (session_factory or _get_session_local())() as db:
                try:
                    return review_queue.refresh(db, UUID(parameters['case_id']))
                finally:
                    db.rollback()
        finally:
            view_cache.always_save.reset(token)
    handler = view_cache.handlers.get(name)
    if handler is None:
        raise LookupError('no cached view named %s' % name)
    arguments = _typed(handler, parameters)
    if view_cache.view_key(name, arguments) != tuple(ask_['key']):
        raise ValueError('the parameters of %s no longer give the same key' % name)
    view_cache.clear()  # never answered from this process's memory: the workers read only the saved copy
    before = dict(view_cache.stats)
    token = view_cache.always_save.set(True)
    try:
        with (session_factory or _get_session_local())() as db:
            try:
                handler(**arguments, db=db)
            except HTTPException as exc:
                if exc.status_code != 422:
                    raise
    finally:
        view_cache.always_save.reset(token)
    after = view_cache.stats
    return after['saved'] > before['saved'] or after['saved_hits'] > before['saved_hits']


def run_child():
    """The refresh process: computes asks until none has come for IDLE_EXIT_SECONDS. One per host (LOCK)."""
    from services.financial import view_cache, view_warmup
    lock = view_warmup._take_lock(name=LOCK)
    if lock is None:
        return 0
    refreshed = 0
    with lock:
        code = view_cache.code_identity()
        idle_since = time.monotonic()
        while time.monotonic() - idle_since < IDLE_EXIT_SECONDS and not view_warmup.process_shutdown_requested():
            asks = [] if view_warmup._preparing() else _open_asks(code)
            if not asks:
                time.sleep(POLL_SECONDS)
                continue
            for path, ask_ in asks:
                started = time.perf_counter()
                _write(path, {**ask_, 'started': dict(pid=os.getpid(), at=time.time())})
                try:
                    kept = refresh_one(path, ask_)
                except Exception as exc:  # noqa: BLE001 - marked failed; its request computes it after the limit
                    logger.warning('Financial view %s refresh failed (%s: %s)', ask_['key'][0], type(exc).__name__, exc)
                    kept = False
                current = _read(path)
                if current is not None and current.get('asked') == ask_['asked']:
                    if kept:
                        path.unlink(missing_ok=True)
                    else:
                        _write(path, {**current, 'failed': time.time()})
                if kept:
                    refreshed += 1
                    logger.info('Financial view %s refreshed for case %s (%.1f s, asked %.0f s before)', ask_['key'][0],
                                ask_['case_id'][:8], time.perf_counter() - started, time.time() - ask_['asked'])
            idle_since = time.monotonic()
    return refreshed


def _child_command():
    import sys
    return [sys.executable, '-m', 'services.financial.view_refresh', CHILD_FLAG]


def _lock_free():
    from services.financial import view_warmup
    lock = view_warmup._take_lock(name=LOCK)
    if lock is None:
        return False
    lock.close()
    return True


async def refresh_loop():
    """In each worker's event loop: start the refresh child when this code has asks and none is running."""
    from pathlib import Path
    from services.financial import view_cache, view_warmup
    if os.environ.get('FINANCIAL_VIEW_UPDATING', '1') == '0':
        return
    backend = Path(__file__).resolve().parents[2]
    while True:
        await asyncio.sleep(POLL_SECONDS)
        try:
            code = view_cache.code_identity()
            if code is None or not _open_asks(code) or not _lock_free():
                continue
            child = await asyncio.create_subprocess_exec(*_child_command(), cwd=str(backend),
                preexec_fn=functools.partial(view_warmup._end_with_parent, os.getpid()))
            try:
                status = await child.wait()
            except asyncio.CancelledError:
                if child.returncode is None:
                    child.terminate()
                raise
            if status:
                logger.warning('Financial view refresh process ended with status %s', status)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - asks stay; the next poll tries again
            logger.warning('Financial view refresh check failed', exc_info=True)
            await asyncio.sleep(30)


if __name__ == '__main__':
    import sys
    if CHILD_FLAG in sys.argv[1:]:
        run_child()
