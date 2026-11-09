"""One agent run reads a case's ledger capture once per account/date scope while the rows it read are unchanged.

Every agent ledger tool (coverage, grouped analysis, payment pages) starts from the same capture of the case's
payments (services.financial.ledger_summary with captured readings). On BNB2 (27,673 payments) that capture is
nearly all of a call's time (measured 2026-11-08: 109 of 125 s for coverage and 57 of 71 s for a month grouping on
the loaded box), and one run asked for it four times for the same scope.

The cache is the run's own (``AgentToolContext.ledger_cache``) and ends with the run. A kept capture is used again
only when the database proves nothing it was computed from has changed: the tables its SQL named are fingerprinted
with the Financial view cache's own check (services.financial.view_cache.fingerprint: per table, the count and an
md5 of the sorted xmin of this case's rows), in the same read-only snapshot the capture was read in, and again in
the later call's snapshot; only an equal fingerprint reuses it. Any write to a row in scope (a correction, a label,
a judgement call, a new statement) changes the fingerprint and the capture is read again. Off on databases other
than PostgreSQL, and when a fingerprint cannot be taken.

Callers share the kept capture and only read it: read_financial_ledger builds every page, total and coverage from
it without changing it (tests/test_agent_lean_history checks every view). It is not copied: copying 27,673 captured
readings took as long as reading them (replay 2026-11-08: a cached call still took 50-126 s on the loaded box).
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Any, Callable

from sqlalchemy import event

log = logging.getLogger(__name__)

# Captures kept per run: a run asks for a few scopes (the whole case, one holder, one account).
MAX_ENTRIES = 3


class LedgerRunCache:
    def __init__(self, max_entries: int = MAX_ENTRIES):
        self.max_entries = max_entries
        self._entries: OrderedDict = OrderedDict()
        self.stats = dict(hits=0, misses=0, changed=0, not_kept=0, check_ms=0)

    def read(self, session, key: tuple, case_id, compute: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        """The capture for ``key``: the kept one when its rows are unchanged in this session's snapshot, else
        ``compute()`` (kept when it can be checked later)."""
        from services.financial import view_cache
        connection = session.connection()
        if connection.dialect.name != "postgresql":
            return compute()
        entry = self._entries.get(key)
        if entry is not None:
            started = time.perf_counter()
            current = view_cache.fingerprint(connection, entry[0], case_id)
            self.stats["check_ms"] += int((time.perf_counter() - started) * 1000)
            if current is not None and current == entry[1]:
                self._entries.move_to_end(key)
                self.stats["hits"] += 1
                return entry[2]
            self.stats["changed"] += 1
            del self._entries[key]
        known = view_cache._load_tables(connection)
        tables: set[str] = set()

        def record(conn, cursor, statement, parameters, context, executemany):
            tables.update(token for token in view_cache._TOKEN.findall(statement.lower()) if token in known)

        event.listen(connection, "before_cursor_execute", record)
        try:
            value = compute()
        finally:
            event.remove(connection, "before_cursor_execute", record)
        self.stats["misses"] += 1
        stamp = view_cache.fingerprint(connection, tables, case_id) if tables and value.get("available") else None
        if stamp is None:
            self.stats["not_kept"] += 1
            return value
        self._entries[key] = (tuple(sorted(tables)), stamp, value)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
        return value
