"""
Docket — ticket store + lifecycle state machine (SQLite).

Docket is the evolution of the QA testing hub into a real ticket pipeline: an
ask is raised in the Discussion zone, **submitted for processing**, then crawls
a visible production line (Queued → Assessment → Planning → In Development →
Self-Review → PR → User Review → Done) driven by an autonomous dev agent. The
board's quiet purpose is to make the *cost* of development legible to testers.

Why SQLite (not the flat JSON the old hub used): tickets need an audit trail,
queue ordering, a streaming work-history, and concurrent writes from three
directions at once (the agent, the UI, and testers). A transactional store in
WAL mode handles that cleanly where reload-and-overwrite JSON would lose writes.

Three tables:
  tickets        — one row per work item (the lifecycle state lives here)
  ticket_events  — append-only work history AND audit log (transitions,
                   the live "currently working on" activity, assessment, plan,
                   comments). The activity ticker = the latest 'activity' event.
  notifications  — outbound notification queue (events → recipient → channel),
                   drained by the notifier (msmtp / in-app badge).

The state machine is the contract: `transition()` REFUSES illegal moves, so no
caller (agent or human) can put a ticket into an impossible state. Every
transition writes a ticket_events row, so the timeline is never out of sync
with the status.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from services._timeutil import utcnow_iso

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "data"
DB_FILE = STORAGE_DIR / "docket.db"

# ---------------------------------------------------------------------------
# Vocabulary: ticket types, priorities, statuses, and the legal transitions.
# ---------------------------------------------------------------------------

TICKET_TYPES = ("bug", "feature")

# Priority scheme (provisional — Neil to confirm). P0 is most urgent; the queue
# is ordered by priority first, then FIFO within a priority (queue_seq).
PRIORITIES = ("P0", "P1", "P2", "P3")
DEFAULT_PRIORITY = "P2"

# Lifecycle statuses. `kind` groups them for the board's swimlanes; `label` is
# the human-facing name shown on cards.
#   discussion  — pre-pipeline: refine the ask, comment, set priority
#   queue       — waiting to be picked up (has a queue position)
#   agent       — the autonomous worker is actively in this stage
#   human_gate  — waiting on a person (Neil's PR review, Alex's user test, info)
#   terminal    — done
STATUS_META: Dict[str, Dict[str, str]] = {
    "discussion":        {"label": "Discussion",        "kind": "discussion"},
    "queued":            {"label": "Queued",            "kind": "queue"},
    "assessment":        {"label": "Assessment",        "kind": "agent"},
    "planning":          {"label": "Planning",          "kind": "agent"},
    "in_development":    {"label": "In Development",    "kind": "agent"},
    "self_review":       {"label": "Self-Review",       "kind": "agent"},
    "pr":                {"label": "PR — Awaiting OK",  "kind": "human_gate"},
    "user_review":       {"label": "User Review",       "kind": "human_gate"},
    "needs_info":        {"label": "Needs Info",        "kind": "human_gate"},
    "changes_requested": {"label": "Changes Requested", "kind": "human_gate"},
    "stalled":           {"label": "Stalled",           "kind": "human_gate"},
    "done":              {"label": "Done",              "kind": "terminal"},
}
STATUSES = tuple(STATUS_META.keys())

# The happy-path order, used for progress bars and "how far along" maths.
MAIN_LINE = (
    "queued", "assessment", "planning", "in_development",
    "self_review", "pr", "user_review", "done",
)

# Stages where the agent is running and so can be flipped to "stalled" by the
# heartbeat watchdog.
AGENT_STAGES = ("assessment", "planning", "in_development", "self_review")

# Allowed transitions: from-status -> set of legal to-statuses. Anything not
# listed here is rejected by transition(). The grooming gate, PR bounce, the
# self-review retry loop, the user-review fail->requeue loop, and the
# needs-info / stalled recovery paths are all encoded here.
TRANSITIONS: Dict[str, set] = {
    "discussion":        {"queued"},
    "queued":            {"assessment", "discussion"},
    "assessment":        {"planning", "needs_info", "stalled"},
    "planning":          {"in_development", "needs_info", "stalled"},
    "in_development":    {"self_review", "needs_info", "stalled"},
    "self_review":       {"pr", "in_development", "stalled"},
    "pr":                {"user_review", "changes_requested"},
    "changes_requested": {"in_development"},
    "user_review":       {"done", "queued", "discussion"},
    # Recovery paths: a bounced/stalled ticket re-enters the pipeline or returns
    # to discussion for amendment.
    "needs_info":        {"queued", "assessment", "planning", "in_development", "discussion"},
    "stalled":           {"queued", "assessment", "planning", "in_development", "needs_info"},
    "done":              {"queued"},  # reopen
}

# ticket_events.kind — what a timeline entry represents.
EVENT_KINDS = ("transition", "activity", "assessment", "plan", "comment", "note")

VALID_NOTIFY_EVENTS = ("needs_info", "pr_ready", "user_review", "stalled", "failed")


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:40] or "ticket"


# ---------------------------------------------------------------------------
# Connection / schema
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # WAL = concurrent readers don't block the single writer; busy_timeout lets
    # a contended write wait rather than fail instantly under the agent+UI load.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT NOT NULL,
    type                TEXT NOT NULL DEFAULT 'feature',
    description         TEXT NOT NULL DEFAULT '',
    acceptance_criteria TEXT NOT NULL DEFAULT '',
    priority            TEXT NOT NULL DEFAULT 'P2',
    status              TEXT NOT NULL DEFAULT 'discussion',
    substage            TEXT NOT NULL DEFAULT '',
    queue_seq           INTEGER,            -- set when entering 'queued'; orders the queue within a priority
    iteration           INTEGER NOT NULL DEFAULT 0,
    branch              TEXT NOT NULL DEFAULT '',
    worktree_path       TEXT NOT NULL DEFAULT '',
    pr_url              TEXT NOT NULL DEFAULT '',
    test_instructions   TEXT NOT NULL DEFAULT '',
    seed_user_item_id   TEXT NOT NULL DEFAULT '',   -- the old-hub user_item this was promoted from
    created_by          TEXT NOT NULL DEFAULT '',
    assignee            TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_queue  ON tickets(status, priority, queue_seq);

CREATE TABLE IF NOT EXISTS ticket_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id  INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    ts         TEXT NOT NULL,
    phase      TEXT NOT NULL DEFAULT '',   -- the status this happened under
    actor      TEXT NOT NULL DEFAULT '',   -- 'agent' or a person's name
    kind       TEXT NOT NULL DEFAULT 'note',
    summary    TEXT NOT NULL DEFAULT '',
    payload    TEXT NOT NULL DEFAULT ''    -- JSON blob for structured detail
);

CREATE INDEX IF NOT EXISTS idx_events_ticket ON ticket_events(ticket_id, id);

CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id  INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    recipient  TEXT NOT NULL,
    channel    TEXT NOT NULL DEFAULT 'email',
    event      TEXT NOT NULL,
    subject    TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | failed
    created_at TEXT NOT NULL,
    sent_at    TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_notif_pending ON notifications(status, id);
"""


def init_db() -> None:
    """Create the schema if it doesn't exist (idempotent)."""
    conn = _connect()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


# Ensure the DB exists as soon as the module is imported.
init_db()


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def ticket_ref(ticket_id: int) -> str:
    """Human-facing id, e.g. DKT-12."""
    return f"DKT-{ticket_id}"


def _row_to_ticket(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["ref"] = ticket_ref(d["id"])
    meta = STATUS_META.get(d["status"], {})
    d["status_label"] = meta.get("label", d["status"])
    d["status_kind"] = meta.get("kind", "")
    return d


def _row_to_event(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    if d.get("payload"):
        try:
            d["payload"] = json.loads(d["payload"])
        except (ValueError, TypeError):
            pass
    return d


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

def create_ticket(
    title: str,
    type: str = "feature",
    description: str = "",
    acceptance_criteria: str = "",
    priority: str = DEFAULT_PRIORITY,
    created_by: str = "",
    seed_user_item_id: str = "",
) -> Dict[str, Any]:
    """Raise a new ticket in the Discussion zone. Returns the created ticket."""
    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")
    if type not in TICKET_TYPES:
        raise ValueError(f"type must be one of {TICKET_TYPES}")
    if priority not in PRIORITIES:
        priority = DEFAULT_PRIORITY
    now = utcnow_iso()

    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO tickets
               (title, type, description, acceptance_criteria, priority, status,
                created_by, seed_user_item_id, created_at, updated_at)
               VALUES (?,?,?,?,?,'discussion',?,?,?,?)""",
            (title[:300], type, str(description)[:20000],
             str(acceptance_criteria)[:10000], priority,
             created_by, seed_user_item_id, now, now),
        )
        tid = cur.lastrowid
        conn.execute(
            """INSERT INTO ticket_events (ticket_id, ts, phase, actor, kind, summary)
               VALUES (?,?,?,?,?,?)""",
            (tid, now, "discussion", created_by or "system", "transition",
             "Ticket created"),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        return _row_to_ticket(row)
    finally:
        conn.close()


def get_ticket(ticket_id: int) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return _row_to_ticket(row) if row else None
    finally:
        conn.close()


def list_tickets(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """All tickets (optionally filtered by status), newest-updated first."""
    conn = _connect()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE status=? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tickets ORDER BY updated_at DESC"
            ).fetchall()
        return [_row_to_ticket(r) for r in rows]
    finally:
        conn.close()


# Fields a caller may patch directly (lifecycle status goes through transition()).
_EDITABLE = {
    "title", "type", "description", "acceptance_criteria", "priority",
    "substage", "branch", "worktree_path", "pr_url", "test_instructions",
    "assignee",
}


def update_ticket(ticket_id: int, **fields) -> Optional[Dict[str, Any]]:
    """Patch editable fields (NOT status — use transition()). Returns the ticket."""
    sets, vals = [], []
    for k, v in fields.items():
        if k not in _EDITABLE:
            raise ValueError(f"field '{k}' is not directly editable")
        if k == "priority" and v not in PRIORITIES:
            continue
        if k == "type" and v not in TICKET_TYPES:
            continue
        sets.append(f"{k}=?")
        vals.append(v)
    if not sets:
        return get_ticket(ticket_id)
    sets.append("updated_at=?")
    vals.append(utcnow_iso())
    vals.append(ticket_id)
    conn = _connect()
    try:
        conn.execute(f"UPDATE tickets SET {', '.join(sets)} WHERE id=?", vals)
        conn.commit()
    finally:
        conn.close()
    return get_ticket(ticket_id)


def transition(
    ticket_id: int,
    to_status: str,
    actor: str = "system",
    summary: str = "",
    payload: Optional[dict] = None,
) -> Dict[str, Any]:
    """Move a ticket to `to_status`, enforcing the state machine.

    Side effects, all in one transaction:
      - validates the (from -> to) move against TRANSITIONS
      - on entering 'queued', assigns the next queue_seq
      - on the user-review fail->requeue loop, bumps `iteration`
      - records a 'transition' event so the timeline stays in sync

    Raises ValueError on an illegal transition or unknown ticket/status.
    """
    if to_status not in STATUSES:
        raise ValueError(f"unknown status '{to_status}'")
    now = utcnow_iso()
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not row:
            raise ValueError(f"ticket {ticket_id} not found")
        cur_status = row["status"]
        if cur_status == to_status:
            # No-op move; record nothing, just return current.
            return _row_to_ticket(row)
        allowed = TRANSITIONS.get(cur_status, set())
        if to_status not in allowed:
            raise ValueError(
                f"illegal transition {cur_status} -> {to_status} "
                f"(allowed: {sorted(allowed)})"
            )

        sets = ["status=?", "updated_at=?"]
        vals: List[Any] = [to_status, now]

        # Entering the queue: stamp a fresh queue_seq (FIFO within a priority).
        if to_status == "queued":
            nxt = conn.execute(
                "SELECT COALESCE(MAX(queue_seq),0)+1 AS n FROM tickets"
            ).fetchone()["n"]
            sets.append("queue_seq=?")
            vals.append(nxt)

        # User-review bounce back into the queue = a new iteration of the ask.
        if cur_status == "user_review" and to_status in ("queued", "discussion"):
            sets.append("iteration=?")
            vals.append(int(row["iteration"]) + 1)

        vals.append(ticket_id)
        conn.execute(f"UPDATE tickets SET {', '.join(sets)} WHERE id=?", vals)
        conn.execute(
            """INSERT INTO ticket_events (ticket_id, ts, phase, actor, kind, summary, payload)
               VALUES (?,?,?,?,?,?,?)""",
            (ticket_id, now, to_status, actor, "transition",
             summary or f"{cur_status} → {to_status}",
             json.dumps(payload) if payload else ""),
        )
        conn.commit()
        out = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return _row_to_ticket(out)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Events (work history + the live activity ticker)
# ---------------------------------------------------------------------------

def add_event(
    ticket_id: int,
    kind: str,
    summary: str = "",
    actor: str = "",
    phase: str = "",
    payload: Optional[dict] = None,
) -> Dict[str, Any]:
    """Append a work-history / audit entry. `phase` defaults to current status."""
    if kind not in EVENT_KINDS:
        raise ValueError(f"kind must be one of {EVENT_KINDS}")
    now = utcnow_iso()
    conn = _connect()
    try:
        if not phase:
            r = conn.execute("SELECT status FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            if not r:
                raise ValueError(f"ticket {ticket_id} not found")
            phase = r["status"]
        cur = conn.execute(
            """INSERT INTO ticket_events (ticket_id, ts, phase, actor, kind, summary, payload)
               VALUES (?,?,?,?,?,?,?)""",
            (ticket_id, now, phase, actor, kind, str(summary)[:5000],
             json.dumps(payload) if payload else ""),
        )
        # Bump the ticket's updated_at so "last activity" reflects the event.
        conn.execute("UPDATE tickets SET updated_at=? WHERE id=?", (now, ticket_id))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM ticket_events WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_event(row)
    finally:
        conn.close()


def set_activity(ticket_id: int, text: str, actor: str = "agent") -> Dict[str, Any]:
    """Update the 'currently working on' ticker (an 'activity' event)."""
    return add_event(ticket_id, "activity", summary=text, actor=actor)


def get_events(ticket_id: int) -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM ticket_events WHERE ticket_id=? ORDER BY id ASC",
            (ticket_id,),
        ).fetchall()
        return [_row_to_event(r) for r in rows]
    finally:
        conn.close()


def current_activity(ticket_id: int) -> Optional[Dict[str, Any]]:
    """The latest 'activity' event — what the agent is doing right now."""
    conn = _connect()
    try:
        row = conn.execute(
            """SELECT * FROM ticket_events
               WHERE ticket_id=? AND kind='activity' ORDER BY id DESC LIMIT 1""",
            (ticket_id,),
        ).fetchone()
        return _row_to_event(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------

def queue() -> List[Dict[str, Any]]:
    """Queued tickets in pick-up order (priority, then FIFO). Each gets a
    1-based `position`."""
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT * FROM tickets WHERE status='queued'
               ORDER BY priority ASC, queue_seq ASC"""
        ).fetchall()
        out = []
        for i, r in enumerate(rows, start=1):
            t = _row_to_ticket(r)
            t["position"] = i
            out.append(t)
        return out
    finally:
        conn.close()


def next_in_queue() -> Optional[Dict[str, Any]]:
    """The ticket the orchestrator should pick up next (highest priority, oldest)."""
    q = queue()
    return q[0] if q else None


def queue_position(ticket_id: int) -> Optional[int]:
    """1-based position of a queued ticket, or None if it isn't queued."""
    for t in queue():
        if t["id"] == ticket_id:
            return t["position"]
    return None


# ---------------------------------------------------------------------------
# Notifications (queued here; drained by the notifier service later)
# ---------------------------------------------------------------------------

def enqueue_notification(
    ticket_id: int, recipient: str, event: str,
    subject: str = "", body: str = "", channel: str = "email",
) -> Dict[str, Any]:
    if event not in VALID_NOTIFY_EVENTS:
        raise ValueError(f"event must be one of {VALID_NOTIFY_EVENTS}")
    now = utcnow_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO notifications
               (ticket_id, recipient, channel, event, subject, body, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (ticket_id, recipient, channel, event, subject, body, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM notifications WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def pending_notifications() -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE status='pending' ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_notification(notif_id: int, status: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE notifications SET status=?, sent_at=? WHERE id=?",
            (status, utcnow_iso() if status == "sent" else "", notif_id),
        )
        conn.commit()
    finally:
        conn.close()
