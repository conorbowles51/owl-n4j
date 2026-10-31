"""Encode route results in a worker thread, not on the event loop.

FastAPI turns every value a route returns (anything but a Response) into JSON-ready data with
``fastapi.routing.serialize_response``: jsonable_encoder, or the response model's validation and
serialisation. It runs that on the event loop for every route, plain-function handlers included, so a
large answer stalls every other request in the worker while it is walked: d5b330d1's engine job list
(3.15 MB) took 0.38 s in jsonable_encoder (measured 2026-10-31).

``install()`` replaces it with a wrapper that runs FastAPI's own function, with the same arguments, in
a worker thread. Same function and arguments, so the same data and the same bytes. jsonable_encoder is
pure Python, so in a thread it hands the interpreter back to the event loop every few milliseconds. The
threads have their own limiter (ENCODE_SLOTS per worker), so an answer never waits behind handlers
holding the default pool. LOUPE_SERIALIZE_OFF_LOOP=0 turns it off.
"""
import asyncio
import inspect
import logging
import os
import weakref

import anyio
import fastapi.routing as routing

ENCODE_SLOTS = 4

_original = routing.serialize_response
# One limiter per event loop: a worker runs one loop, a test process may run several.
_limiters = weakref.WeakKeyDictionary()


def _encode(arguments):
    # is_coroutine=True: FastAPI then validates inline (it is already in a thread) and the coroutine
    # finishes without suspending; driving it to completion here returns its value.
    coroutine = _original(**{**arguments, 'is_coroutine': True})
    try:
        coroutine.send(None)
    except StopIteration as done:
        return done.value
    coroutine.close()
    raise RuntimeError('serialize_response suspended in a worker thread')


async def serialize_response(**arguments):
    loop = asyncio.get_running_loop()
    limiter = _limiters.get(loop)
    if limiter is None:
        limiter = _limiters[loop] = anyio.CapacityLimiter(ENCODE_SLOTS)
    return await anyio.to_thread.run_sync(_encode, arguments, limiter=limiter)


def install():
    """Route every FastAPI result encoding through the worker thread; False when switched off."""
    if os.environ.get('LOUPE_SERIALIZE_OFF_LOOP', '1') == '0':
        return False
    if 'is_coroutine' not in inspect.signature(_original).parameters:
        # A FastAPI upgrade changed it: encode on the loop as FastAPI does (tests/test_response_encoding fails).
        logging.getLogger(__name__).warning('fastapi.routing.serialize_response changed; encoding stays on the loop')
        return False
    routing.serialize_response = serialize_response
    return True
