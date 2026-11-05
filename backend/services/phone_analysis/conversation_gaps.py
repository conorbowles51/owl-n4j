"""Holes in a phone's conversations (docs/cellebrite/05 section 6.3 step 3): the one rule both readers use.

Approach 3 (``deletion_timeline``) reports the holes; approach 2 (``message_reconciliation``) gives "the other phone's
conversation has a gap here" as a reason a message is on one phone only (5.3.6). Approach 3 also reads approach 2's
matches (19.S6-c), so the rule lives here, beneath both, and reads records only: neither approach reads the other's
results for it, and a run of one never depends on a run of the other.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import text

HOLE_MIN_DAYS = 7
DELETED = ("Deleted", "Trash")
MIN_INTACT = 3


def _percentile(values, pct):
    """Nearest-rank percentile."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(pct / 100.0 * len(s)) - 1)]


def holes_in(times: list, min_gap: timedelta) -> list:
    """Gaps between consecutive intact message times longer than ``min_gap`` and longer than the 99th percentile of
    the conversation's other gaps (19.S6-a). ``times`` sorted. Returns [(start, end)]."""
    gaps = [(times[i], times[i + 1]) for i in range(len(times) - 1)]
    if len(gaps) < 2:
        return []
    secs = [(b - a).total_seconds() for a, b in gaps]
    out = []
    for i, (a, b) in enumerate(gaps):
        if secs[i] <= min_gap.total_seconds():
            continue
        others = secs[:i] + secs[i + 1:]
        if secs[i] > _percentile(others, 99):
            out.append((a, b))
    return out


def phone_messages(conn, ext) -> list:
    return conn.execute(text(
        "SELECT record_uid::text AS uid, thread_key, coalesce(app, '') AS app, sort_instant, deleted_state FROM "
        "pv_comm_event WHERE extraction_id = :e AND kind = 'message'"), {"e": ext}).mappings().all()


def conversations(msgs) -> dict:
    convs = defaultdict(list)
    for m in msgs:
        if m["thread_key"]:
            convs[(m["app"], m["thread_key"])].append(m)
    return convs


def conversation_holes(msgs, min_gap: timedelta, convs=None) -> tuple:
    """(holes, gaps_without_app_data). A hole is ``{"key": (app, thread), "start", "end", "before", "after",
    "elsewhere"}``: ``before`` and ``after`` are the intact messages bounding it, ``elsewhere`` the app's messages in
    other conversations inside the gap. A gap in which the app recorded nothing at all on the phone is that app's
    no-data period, not a hole (19.S6-b)."""
    convs = conversations(msgs) if convs is None else convs
    app_times = defaultdict(list)
    for m in msgs:
        if m["sort_instant"]:
            app_times[m["app"]].append((m["sort_instant"], m["thread_key"]))
    holes, no_app_data = [], 0
    for key, ms in convs.items():
        intact = sorted((m["sort_instant"], m["uid"]) for m in ms if m["sort_instant"] and m["deleted_state"] not in
                        DELETED)
        if len(intact) < MIN_INTACT:
            continue
        uid_at = {}
        for t, u in intact:
            uid_at.setdefault(t, u)
        for a, b in holes_in([t for t, _ in intact], min_gap):
            elsewhere = sum(1 for t, th in app_times[key[0]] if a < t < b and th != key[1])
            if not elsewhere:
                no_app_data += 1
                continue
            holes.append({"key": key, "start": a, "end": b, "before": uid_at[a], "after": uid_at[b],
                          "elsewhere": elsewhere})
    return holes, no_app_data


def phone_holes(conn, ext) -> dict:
    """``{thread_key: [hole, ...]}`` at approach 3's default threshold."""
    holes, _ = conversation_holes(phone_messages(conn, ext), timedelta(days=HOLE_MIN_DAYS))
    out = defaultdict(list)
    for h in holes:
        out[h["key"][1]].append(h)
    return dict(out)
