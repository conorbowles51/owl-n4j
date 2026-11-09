"""One person's steps through one case: the history strip (lx-guide H-K).

A step is what was on screen: the screen, the address, the full view state (selected item, filters, sort, date
range, scroll anchor by item key, open panel) and a plain name ("Transactions · BBVA 0110280038 · Nov 2022"). Steps
are private to the person, kept 90 days, and cleared by them at will. The browser decides when a change is too small
for a new step and sends ``replaces`` with the id of the person's latest step; only that latest step is ever
rewritten.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

KEEP_DAYS = 90
MAX_NAME = 200
MAX_PATH = 2000
MAX_STATE_BYTES = 16_000
SCREEN_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
LIST_MAX = 500


class StepError(ValueError):
    pass


def _row(r) -> dict:
    return {"id": str(r.id), "at": r.at.isoformat(), "name": r.name, "screen": r.screen, "path": r.path,
            "state": r.state or {}, "item": r.item}


def _clean(name: str, screen: str, path: str, state, item) -> tuple[str, str, str, str, str | None]:
    name = " ".join(str(name or "").split())
    if not name:
        raise StepError("A step needs a name.")
    name = name[:MAX_NAME]
    if not screen or len(screen) > 40 or not set(screen) <= SCREEN_CHARS:
        raise StepError("A step's screen is lower-case letters, digits, '-' or '_'.")
    if not str(path).startswith("/cases/") or len(path) > MAX_PATH:
        raise StepError("A step's address is a case address of up to 2,000 characters.")
    state_json = json.dumps(state if isinstance(state, dict) else {}, separators=(",", ":"))
    if len(state_json.encode()) > MAX_STATE_BYTES:
        raise StepError(f"A step's view state is at most {MAX_STATE_BYTES:,} bytes; this one is "
                        f"{len(state_json.encode()):,}.")
    item_json = None
    if item is not None:
        if not isinstance(item, dict) or not item.get("kind") or not item.get("id"):
            raise StepError("A step's item is {kind, id, label}.")
        item_json = json.dumps({k: str(item[k])[:300] for k in ("kind", "id", "label") if item.get(k)})
    return name, screen, path, state_json, item_json


def prune(conn, user_id, case_id, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=KEEP_DAYS)
    return conn.execute(text("DELETE FROM case_steps WHERE user_id = :u AND case_id = :c AND at < :t"),
                        {"u": str(user_id), "c": str(case_id), "t": cutoff}).rowcount


def latest(conn, user_id, case_id) -> dict | None:
    r = conn.execute(text("SELECT * FROM case_steps WHERE user_id = :u AND case_id = :c ORDER BY at DESC, id LIMIT 1"),
                     {"u": str(user_id), "c": str(case_id)}).first()
    return _row(r) if r else None


def record(conn, user_id, case_id, *, name, screen, path, state=None, item=None, replaces=None) -> dict:
    """Add a step, or rewrite the latest one when ``replaces`` names it (a small change merged into the last step).
    A ``replaces`` that is not the person's latest step adds a new step instead, so no earlier step is rewritten."""
    name, screen, path, state_json, item_json = _clean(name, screen, path, state, item)
    prune(conn, user_id, case_id)
    last = latest(conn, user_id, case_id)
    params = {"u": str(user_id), "c": str(case_id), "n": name, "s": screen, "p": path, "st": state_json,
              "it": item_json}
    if replaces and last and last["id"] == str(replaces):
        r = conn.execute(text("UPDATE case_steps SET name = :n, screen = :s, path = :p, state = CAST(:st AS jsonb), "
                              "item = CAST(:it AS jsonb), at = clock_timestamp() WHERE id = :id RETURNING *"),
                         {**params, "id": last["id"]}).first()
        return {**_row(r), "merged": True}
    if last and (last["path"], last["state"], last["name"]) == (path, json.loads(state_json), name):
        return {**last, "merged": True}  # the same view again (a reload, Back to it): one step, not two
    r = conn.execute(text("INSERT INTO case_steps (id, case_id, user_id, at, name, screen, path, state, item) VALUES "
                          "(:id, :c, :u, clock_timestamp(), :n, :s, :p, CAST(:st AS jsonb), CAST(:it AS jsonb)) RETURNING *"),
                     {**params, "id": str(uuid.uuid4())}).first()
    return {**_row(r), "merged": False}


def listing(conn, user_id, case_id, *, limit: int = 8, q: str | None = None, offset: int = 0) -> dict:
    """The person's steps in this case, newest first, with how many there are in all (so a short list says so)."""
    limit = max(1, min(int(limit), LIST_MAX))
    where = "user_id = :u AND case_id = :c AND at >= now() - make_interval(days => :d)"
    params = {"u": str(user_id), "c": str(case_id), "d": KEEP_DAYS}
    if q and q.strip():
        where += " AND (name ILIKE :q OR screen ILIKE :q)"
        params["q"] = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    total = conn.execute(text(f"SELECT count(*) FROM case_steps WHERE {where}"), params).scalar_one()
    rows = conn.execute(text(f"SELECT * FROM case_steps WHERE {where} ORDER BY at DESC, id LIMIT :l OFFSET :o"),
                        {**params, "l": limit, "o": max(0, int(offset))}).all()
    return {"steps": [_row(r) for r in rows], "total": total, "keep_days": KEEP_DAYS}


def get(conn, user_id, case_id, step_id) -> dict | None:
    try:
        sid = str(uuid.UUID(str(step_id)))
    except ValueError:
        return None
    r = conn.execute(text("SELECT * FROM case_steps WHERE id = :i AND user_id = :u AND case_id = :c"),
                     {"i": sid, "u": str(user_id), "c": str(case_id)}).first()
    return _row(r) if r else None


def clear(conn, user_id, case_id) -> int:
    return conn.execute(text("DELETE FROM case_steps WHERE user_id = :u AND case_id = :c"),
                        {"u": str(user_id), "c": str(case_id)}).rowcount
