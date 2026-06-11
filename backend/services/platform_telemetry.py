"""
Platform telemetry — lightweight per-route traffic/error/latency capture.

The point: once a Docket ticket ships, its real-world performance should be
measured automatically (testers won't reliably hand-rate features). Every
request is aggregated as (day, route-template, method, status) → count +
total latency, so Docket can later join a shipped ticket's `touched_routes`
against actual traffic: is the feature used, and is it erroring?

Design constraints:
  - Near-zero overhead: requests increment an in-process buffer; the buffer is
    flushed to SQLite at most every FLUSH_SECS (or when it grows large), so the
    hot path never touches disk.
  - Multi-worker safe: flushes are additive upserts (ON CONFLICT … n = n + new)
    into data/telemetry.db in WAL mode, so concurrent uvicorn workers can't
    clobber each other (cf. the JSON-storage lesson).
  - Route TEMPLATES only (e.g. /api/tickets/{ticket_id}), never raw paths, so
    cardinality stays bounded and IDs don't leak into analytics.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_FILE = BASE_DIR / "data" / "telemetry.db"

FLUSH_SECS = 30          # max staleness of the on-disk aggregates
FLUSH_MAX_KEYS = 500     # safety valve: flush early if the buffer grows big

_SCHEMA = """
CREATE TABLE IF NOT EXISTS route_traffic (
    day      TEXT NOT NULL,      -- UTC date, YYYY-MM-DD
    route    TEXT NOT NULL,      -- route template, e.g. /api/tickets/{ticket_id}
    method   TEXT NOT NULL,
    status   INTEGER NOT NULL,
    n        INTEGER NOT NULL DEFAULT 0,
    total_ms REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (day, route, method, status)
);
"""

_buf: Dict[tuple, List[float]] = {}   # (day, route, method, status) -> [n, total_ms]
_buf_lock = threading.Lock()
_last_flush = 0.0


def _connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def record(route: str, method: str, status: int, ms: float) -> None:
    """Count one request (hot path: in-memory; flushed periodically)."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = (day, route, method.upper(), int(status))
    flush_now = False
    with _buf_lock:
        slot = _buf.setdefault(key, [0, 0.0])
        slot[0] += 1
        slot[1] += ms
        if (len(_buf) >= FLUSH_MAX_KEYS
                or time.monotonic() - _last_flush >= FLUSH_SECS):
            flush_now = True
    if flush_now:
        flush()


def flush() -> None:
    """Additively upsert the buffer into SQLite (safe across workers)."""
    global _last_flush
    with _buf_lock:
        items = list(_buf.items())
        _buf.clear()
        _last_flush = time.monotonic()
    if not items:
        return
    try:
        conn = _connect()
        try:
            conn.executemany(
                """INSERT INTO route_traffic (day, route, method, status, n, total_ms)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(day, route, method, status)
                   DO UPDATE SET n = n + excluded.n,
                                 total_ms = total_ms + excluded.total_ms""",
                [(d, r, m, s, v[0], v[1]) for (d, r, m, s), v in items],
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        pass  # telemetry must never take the app down


def route_stats(routes: List[str], since_day: Optional[str] = None,
                until_day: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate traffic for the given route templates in [since_day, until_day]
    (inclusive UTC dates). Returns hits / errors (5xx) / avg latency."""
    if not routes:
        return {"hits": 0, "errors": 0, "err_rate": 0.0, "avg_ms": None}
    flush()
    q = (f"SELECT status, SUM(n) AS n, SUM(total_ms) AS ms FROM route_traffic "
         f"WHERE route IN ({','.join('?' * len(routes))})")
    args: List[Any] = list(routes)
    if since_day:
        q += " AND day >= ?"; args.append(since_day)
    if until_day:
        q += " AND day <= ?"; args.append(until_day)
    q += " GROUP BY status"
    conn = _connect()
    try:
        conn.executescript(_SCHEMA)
        rows = conn.execute(q, args).fetchall()
    finally:
        conn.close()
    hits = sum(r["n"] for r in rows)
    errors = sum(r["n"] for r in rows if r["status"] >= 500)
    ms = sum(r["ms"] for r in rows)
    return {"hits": hits, "errors": errors,
            "err_rate": round(errors / hits, 4) if hits else 0.0,
            "avg_ms": round(ms / hits, 1) if hits else None}


def global_stats(since_day: Optional[str] = None,
                 until_day: Optional[str] = None) -> Dict[str, Any]:
    """Platform-wide traffic/error aggregate — used to spot collateral damage:
    a feature whose own routes look clean but whose ship coincides with a
    platform-wide error spike."""
    flush()
    q = "SELECT status, SUM(n) AS n, SUM(total_ms) AS ms FROM route_traffic WHERE 1=1"
    args: List[Any] = []
    if since_day:
        q += " AND day >= ?"; args.append(since_day)
    if until_day:
        q += " AND day <= ?"; args.append(until_day)
    q += " GROUP BY status"
    conn = _connect()
    try:
        conn.executescript(_SCHEMA)
        rows = conn.execute(q, args).fetchall()
    finally:
        conn.close()
    hits = sum(r["n"] for r in rows)
    errors = sum(r["n"] for r in rows if r["status"] >= 500)
    return {"hits": hits, "errors": errors,
            "err_rate": round(errors / hits, 4) if hits else 0.0}


def install(app) -> None:
    """Attach the capture middleware to a FastAPI app."""
    init_db()

    @app.middleware("http")
    async def _telemetry(request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        try:
            route = request.scope.get("route")
            template = getattr(route, "path", None)
            if template:  # unmatched paths (404 scans etc.) are not recorded
                record(template, request.method, response.status_code,
                       (time.monotonic() - start) * 1000.0)
        except Exception:
            pass  # never let telemetry break a request
        return response
