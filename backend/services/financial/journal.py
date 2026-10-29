"""Loggers whose INFO lines reach the service journal.

The backend runs under uvicorn, which configures only its own loggers; the root
logger has no handler, so Python prints a module's WARNING and above through its
last-resort handler and drops every INFO line. A decision a reader makes (why a
statement was or was not read, what a background round did) must be
reconstructable from the journal, so these loggers carry their own handler at
INFO, writing to stderr (which systemd keeps). Idempotent per logger.
"""
from __future__ import annotations

import logging
import sys

_FORMAT = '%(levelname)s %(name)s: %(message)s'


def journal(name):
    logger = logging.getLogger(name)
    if not any(getattr(handler, '_loupe_journal', False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_FORMAT))
        handler._loupe_journal = True
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # Its own handler: not printed a second time by a root handler some other code may add.
    logger.propagate = False
    return logger
