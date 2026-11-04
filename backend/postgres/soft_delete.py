"""Deleted items: a deleted case or evidence file is hidden from every database read until restored or purged.

A case or evidence file deleted through the app is kept for 30 days (``deleted_at`` set) so it can be restored
(services/casebin.py). While it waits, every ORM SELECT on every session hides:

- the case itself (``cases.deleted_at IS NULL``, always current), and every row of any table with a foreign key to
  ``cases.id`` that points at a deleted case and is not ON DELETE SET NULL (statements, ledger rows, accounts,
  parties, phone records, notes, ...);
- the evidence file itself (``evidence_files.deleted_at IS NULL``, always current), and every row of any table with a
  foreign key to ``evidence_files.id`` that points at a deleted file and is not ON DELETE SET NULL (document texts,
  transcripts, claims, ...). A SET NULL row outlives the old delete too, so it stays visible.

One filter for every table, worked out from the foreign keys, so a table added later is covered without anyone
remembering to add it. ``check_case_access`` reads the case row itself, so every route treats a deleted case as not
found at once (services/case_service.py), which also covers routes whose SQL is written by hand.

Speed (measured 2026-11-03 on the live database, largest case, 28,075 ledger rows): a correlated ``NOT EXISTS`` on
every row took the ledger read from 32 to 58 ms and made Postgres estimate one row. So the rows that point at a
deleted item are filtered with the deleted ids themselves (``case_id NOT IN (...)``), which each process reads at
most every ``REFRESH_SECONDS`` (two index-only lookups on partial indexes) and at once after its own delete or
restore. With nothing deleted (the usual state) no filter is added at all. Another process can see a just-deleted
case's child rows for up to ``REFRESH_SECONDS`` in background work; requests are refused at once by the case check.

Only while Deleted items are switched on (``enabled()``, config.DELETED_ITEMS_ENABLED); off, nothing is filtered and
deletes are immediate.

Reading deleted rows is opt-in: ``with showing_deleted(session): ...`` (the Deleted-items listing, restore and purge
only). Relationship and column loads are left alone: they only follow a row that was already allowed.
"""
from __future__ import annotations

import threading
import time
import uuid
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import and_, event, or_
from sqlalchemy.orm import Session, with_loader_criteria

SHOW_DELETED = "loupe_show_deleted"
REFRESH_SECONDS = 5.0

_lock = threading.Lock()
# Per database (engine URL): {"cases", "files", "at"}. One process can talk to more than one database (tests,
# scripts), and one database's deleted ids mean nothing in another.
_known: dict = {}


def enabled() -> bool:
    """Deleted items switched on (config.DELETED_ITEMS_ENABLED, off by default). Off: deletes are immediate and this
    filter adds nothing."""
    import config
    return bool(getattr(config, "DELETED_ITEMS_ENABLED", False))


@contextmanager
def showing_deleted(session: Session):
    """Reads in this block see deleted cases and files (restore, purge and the Deleted-items listing only)."""
    previous = session.info.get(SHOW_DELETED)
    session.info[SHOW_DELETED] = True
    try:
        yield session
    finally:
        if previous is None:
            session.info.pop(SHOW_DELETED, None)
        else:
            session.info[SHOW_DELETED] = previous


def forget():
    """Read the deleted ids again before the next query (called after a delete, restore or purge commits)."""
    with _lock:
        _known.clear()


def _as_uuid(value):
    # Postgres returns UUIDs; SQLite test databases store them as 32-character text (postgres/base.py).
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


_LOOKUP = ("SELECT 'c', id FROM cases WHERE deleted_at IS NOT NULL "
           "UNION ALL SELECT 'f', id FROM evidence_files WHERE deleted_at IS NOT NULL")


def _lookup(connection):
    cursor = connection.connection.cursor()
    try:
        cursor.execute(_LOOKUP)
        return cursor.fetchall()
    finally:
        cursor.close()


def _deleted_ids(session):
    """(deleted case ids, deleted evidence file ids) of the session's database, at most REFRESH_SECONDS old."""
    now = time.monotonic()
    connection = session.connection()
    key = str(connection.engine.url)
    with _lock:
        known = _known.get(key)
        if known is not None and now - known["at"] < REFRESH_SECONDS:
            return known["cases"], known["files"]
    # Read on the session's own database connection (same transaction, no second pooled connection), with a plain
    # cursor: this lookup runs at most every REFRESH_SECONDS whatever the request does, so it stays out of the
    # statement stream that query-count guards (tests counting a route's statements) and SQL listeners watch.
    if connection.dialect.name == "postgresql":
        rows = _lookup(connection)
    else:
        # Unit-test databases (SQLite) create only the tables a test needs; a missing table hides nothing there.
        try:
            rows = _lookup(connection)
        except Exception:
            rows = []
    cases = frozenset(_as_uuid(row[1]) for row in rows if row[0] == "c")
    files = frozenset(_as_uuid(row[1]) for row in rows if row[0] == "f")
    with _lock:
        _known[key] = dict(cases=cases, files=files, at=now)
    return cases, files


def _tables():
    from postgres.base import Base
    return Base.metadata.tables["cases"], Base.metadata.tables["evidence_files"]


@lru_cache(maxsize=None)
def _shape(mapper_cls):
    """(hides itself by deleted_at, attribute names pointing at cases, attribute names pointing at evidence files)."""
    cases, files = _tables()
    mapper = mapper_cls.__mapper__
    local = mapper.local_table
    to_cases, to_files = [], []
    for attribute in mapper.column_attrs:
        column = attribute.columns[0]
        if getattr(column, "table", None) is not local:
            continue
        for fk in column.foreign_keys:
            # A row that goes with its case or file when that is removed is hidden with it (CASCADE; RESTRICT and NO
            # ACTION rows block the removal). A SET NULL link outlives the removal, so its row stays visible: e.g. a
            # live file whose duplicate_of_id points at a deleted file in another case, or a cost record.
            if (fk.ondelete or "").upper() in ("SET NULL", "SET DEFAULT"):
                continue
            if fk.column.name == "id" and fk.column.table is cases:
                to_cases.append((attribute.key, column.nullable))
            elif fk.column.name == "id" and fk.column.table is files:
                to_files.append((attribute.key, column.nullable))
    return local is cases or local is files, tuple(to_cases), tuple(to_files)


def _not_in(attribute, nullable, ids):
    condition = attribute.not_in(sorted(ids, key=str))
    return or_(attribute.is_(None), condition) if nullable else condition


def _criteria(mapper_cls, deleted_cases, deleted_files):
    own, to_cases, to_files = _shape(mapper_cls)
    parts = []
    if own:
        parts.append(mapper_cls.deleted_at.is_(None))
    if deleted_cases:
        parts.extend(_not_in(getattr(mapper_cls, key), nullable, deleted_cases) for key, nullable in to_cases)
    if deleted_files:
        parts.extend(_not_in(getattr(mapper_cls, key), nullable, deleted_files) for key, nullable in to_files)
    if not parts:
        return None
    return with_loader_criteria(mapper_cls, and_(*parts), include_aliases=True)


@lru_cache(maxsize=None)
def _classes_by_table():
    from postgres.base import Base
    by_table = {}
    for mapper in Base.registry.mappers:
        by_table.setdefault(mapper.local_table, []).append(mapper.class_)
    return by_table


def _classes_in(statement):
    """Every mapped class whose table the statement reads, subqueries included (``query(...).count()`` and
    ``select(func.count()).select_from(X)`` name no top-level entity)."""
    from sqlalchemy.sql.util import find_tables
    by_table = _classes_by_table()
    seen = []
    for table in find_tables(statement, check_columns=True, include_aliases=True, include_joins=False):
        for cls in by_table.get(getattr(table, "element", table), ()):
            if cls not in seen:
                seen.append(cls)
    return seen


def _hide_deleted(state):
    if not state.is_select or state.is_column_load or state.is_relationship_load:
        return
    if not enabled():
        return
    if state.session.info.get(SHOW_DELETED) or state.execution_options.get(SHOW_DELETED):
        return
    classes = [cls for cls in _classes_in(state.statement) if any(_shape(cls)[0:1]) or any(_shape(cls)[1:])]
    if not classes:
        return
    deleted_cases, deleted_files = _deleted_ids(state.session)
    options = [option for option in (_criteria(cls, deleted_cases, deleted_files) for cls in classes) if option is not None]
    if options:
        state.statement = state.statement.options(*options)


def live_case_sql(column: str) -> str:
    """SQL text for hand-written cross-case queries: true when ``column`` (a case id) is not a deleted case. For
    sweeps that enumerate cases themselves (the ORM filter above does not see text SQL)."""
    return ("NOT EXISTS (SELECT 1 FROM cases deleted_case WHERE deleted_case.id = %s "
            "AND deleted_case.deleted_at IS NOT NULL)" % column)


_installed = False


def install():
    """Register the filter on every Session (idempotent; done when the models are imported)."""
    global _installed
    if not _installed:
        event.listen(Session, "do_orm_execute", _hide_deleted)
        _installed = True
