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


_PLAIN = (str, int, float, bool)


def _plain(value):
    """True when jsonable_encoder would hand back the same data: only exact dicts with str keys (none starting
    "_sa", which it drops), lists, str, int, float, bool and None. Subclasses (enums, OrderedDict) are not plain."""
    kind = type(value)
    if kind is dict:
        return all(type(key) is str and not key.startswith('_sa') and _plain(item) for key, item in value.items())
    if kind is list:
        return all(_plain(item) for item in value)
    return value is None or kind in _PLAIN


def _encode(arguments):
    # A route without a response model that returns data already in JSON form (most of them: engine job lists,
    # dicts of str and numbers) needs no encoding: checking that costs d5b330d1's jobs list 0.02 s where
    # jsonable_encoder took 0.19 s (31 Oct). Anything else goes through FastAPI's own function, as before.
    if arguments.get('field') is None:
        content = arguments.get('response_content')
        try:
            if _plain(content):
                return content
        except RecursionError:
            pass
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
