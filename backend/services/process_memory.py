"""Keep the cyclic garbage collector's full passes proportional to the work in flight.

uvicorn checks each worker with a ping answered by a thread of that worker, so
anything that holds the GIL for seconds can get a busy worker killed, with its
statement saves and preparations in flight. A full collection walks every
tracked container with the GIL held; ~700k of them are the application itself
(modules, routes, models, settings, clients), loaded at startup and alive
until the process ends. Freezing them once startup is done takes them out of
every later pass (CPython's gc.freeze, intended for exactly this). Objects
created afterwards are collected as before.
"""
import gc


def freeze_startup_objects():
    """Collect once, then move every object alive now out of later collections. Returns the frozen count."""
    gc.collect()
    gc.freeze()
    return gc.get_freeze_count()
