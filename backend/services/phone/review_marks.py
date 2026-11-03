"""Thread review marks (07 section 6.1 "Review marks"; J-13, J-13b, CO-20).

A review mark is a ``case_task_links`` row with target type ``phone_thread`` on the case's phone review task. Its
source anchor holds who reviewed, when, the scope, the number of messages the thread held at that moment and the
reading position, plus the mapping version set ``link_types.phone_anchor`` adds. Marking a thread again keeps the
earlier marks in ``earlier`` (nothing a person did is overwritten); Undo removes the latest mark and puts the one
before it back. Every mark and undo is written to the audit log.

"Added since" is the thread's message count now minus the count at review time, so a Replace that adds messages
makes a reviewed thread partly reviewed (J-13b) without anyone touching the mark.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from services.phone import time_display as T

REVIEW_TASK_TITLE = "Review the phone conversations"
REVIEW_TASK_DESCRIPTION = ("Threads marked reviewed in Conversations. Each link records who reviewed the thread, "
                           "when, and how many messages it held then.")


class ReviewMarkError(ValueError):
    pass


def _task_id(conn, case_id, user_id, *, create):
    row = conn.execute(text(
        "SELECT id FROM case_tasks WHERE case_id = :c AND title = :t AND deleted_at IS NULL ORDER BY created_at "
        "LIMIT 1"), {"c": case_id, "t": REVIEW_TASK_TITLE}).first()
    if row or not create:
        return row[0] if row else None
    tid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO case_tasks (id, case_id, title, description, status, priority, created_by_user_id, "
        "updated_by_user_id, created_at, updated_at) VALUES (:i, :c, :t, :d, 'in_progress', 'standard', :u, :u, "
        "now(), now())"), {"i": tid, "c": case_id, "t": REVIEW_TASK_TITLE, "d": REVIEW_TASK_DESCRIPTION,
                           "u": user_id})
    return tid


def marks(conn, case_id) -> dict:
    """``{thread_key: anchor}`` for every thread with a review mark in the case."""
    out = {}
    for r in conn.execute(text(
            "SELECT l.target_id, l.source_anchor FROM case_task_links l JOIN case_tasks t ON t.id = l.task_id "
            "WHERE l.case_id = :c AND l.target_type = 'phone_thread' AND t.title = :t AND t.deleted_at IS NULL"),
            {"c": case_id, "t": REVIEW_TASK_TITLE}):
        anchor = r.source_anchor if isinstance(r.source_anchor, dict) else {}
        if anchor.get("reviewed_at"):
            out[r.target_id] = anchor
    if out:
        for key, anchor in _carried(conn, case_id, out).items():
            out.setdefault(key, anchor)  # a mark made on the newer report's thread is its own and wins
    return out


_SIGNATURE = "t.app, t.thread_kind, t.chat_type, t.title_in_record, t.party_identity_keys"


def _signature(r) -> tuple:
    return (r.app, r.thread_kind, r.chat_type, r.title_in_record, tuple(sorted(r.party_identity_keys or ())))


def _threads(conn, ext):
    return conn.execute(text(
        "SELECT t.thread_key, " + _SIGNATURE + " FROM phone_threads t JOIN phone_interpretation_state st ON "
        "st.extraction_id = t.extraction_id AND st.generation = t.generation WHERE t.extraction_id = :e"),
        {"e": ext}).fetchall()


def _carried(conn, case_id, marked: dict) -> dict:
    """Marks on threads of a replaced report, carried to the same thread in the report that replaced it (J-13b).

    A thread key holds its report's extraction id (02 decision 45), so after a Replace the same conversation has a
    new key. It is found by the key with the newer report's id put in (the rest of most keys is a hash of the
    thread's own values), or else by app, kind, chat type, title and the people in it, when exactly one thread on
    each side has them. A thread that cannot be matched one to one keeps no mark: a review is never claimed for a
    thread nobody reviewed. The carried mark keeps the count at review time, so messages the newer report adds show
    as "added since"."""
    rows = conn.execute(text(
        "SELECT t.thread_key, t.extraction_id, " + _SIGNATURE + " FROM phone_threads t JOIN "
        "phone_interpretation_state st ON st.extraction_id = t.extraction_id AND st.generation = t.generation JOIN "
        "phone_extractions e ON e.id = t.extraction_id WHERE t.case_id = :c AND e.standing <> 'active' AND "
        "t.thread_key = ANY(:k)"), {"c": str(case_id), "k": list(marked)}).fetchall()
    if not rows:
        return {}
    newer_of = {str(r.supersedes_id): str(r.id) for r in conn.execute(text(
        "SELECT id, supersedes_id FROM phone_extractions WHERE case_id = :c AND supersedes_id IS NOT NULL"),
        {"c": str(case_id)})}
    active = {str(r[0]) for r in conn.execute(text(
        "SELECT id FROM phone_extractions WHERE case_id = :c AND standing = 'active'"), {"c": str(case_id)})}
    out, cache = {}, {}

    def threads(ext):
        if ext not in cache:
            ts = _threads(conn, ext)
            cache[ext] = ({t.thread_key for t in ts}, ts)
        return cache[ext]

    for r in rows:
        key, ext, sig, seen = r.thread_key, str(r.extraction_id), _signature(r), set()
        while key is not None and ext in newer_of and ext not in seen:  # a chain of Replaces, to the active report
            seen.add(ext)
            new_ext = newer_of[ext]
            new_keys, new_ts = threads(new_ext)
            direct = key.replace(ext, new_ext) if ext in key else None
            if direct in new_keys:
                key = direct
            else:
                same_old = [t for t in threads(ext)[1] if _signature(t) == sig]
                same_new = [t.thread_key for t in new_ts if _signature(t) == sig]
                key = same_new[0] if len(same_old) == 1 and len(same_new) == 1 else None
            ext = new_ext
        if key is not None and key != r.thread_key and ext in active:
            out[key] = dict(marked[r.thread_key], carried_from=r.thread_key)
    return out


def review_words(anchor: dict, total_now: int) -> dict:
    """The review block of a thread row: who, when, the count then, what was added since, and the sentence
    "Reviewed by [name] on [date] (N messages); M added since" (6.7)."""
    count = int(anchor.get("record_count") or 0)
    added = max(0, int(total_now) - count)
    when = anchor.get("reviewed_at")
    try:
        day = T.format_full(datetime.fromisoformat(when), "UTC").split(",", 2)
        date_words = ",".join(day[:2]).strip() if len(day) >= 2 else when
    except (TypeError, ValueError):
        date_words = when
    sentence = "Reviewed by %s on %s (%s message%s)" % (anchor.get("reviewed_by_name") or "a person", date_words,
                                                       "{:,}".format(count), "" if count == 1 else "s")
    if added:
        sentence += "; %s added since" % "{:,}".format(added)
    return {"by": anchor.get("reviewed_by_name"), "at": when, "record_count": count, "added_since": added,
            "words": sentence}


def mark(db, case_id, thread_key: str, user, *, scope=None, position=None) -> dict:
    """Mark a thread reviewed now. Returns the review block."""
    from postgres import link_types
    from services.phone.streams import NO_THREAD_PREFIX
    from services.system_log_service import LogOrigin, LogType, system_log_service
    conn = db.connection()
    if thread_key.startswith(NO_THREAD_PREFIX):
        ext = thread_key[len(NO_THREAD_PREFIX):]
        total = conn.execute(text(
            "SELECT count(*) FROM phone_comm_events ev JOIN phone_interpretation_state st ON st.extraction_id = "
            "ev.extraction_id AND st.generation = ev.generation JOIN phone_extractions e ON e.id = ev.extraction_id "
            "WHERE e.case_id = :c AND e.standing = 'active' AND ev.thread_key IS NULL AND ev.extraction_id::text = :e"),
            {"c": case_id, "e": ext}).scalar()
        if not total:
            raise ReviewMarkError("This conversation is not in the case.")
        anchor = {"mapping_versions": {}}
    else:
        try:
            target = link_types.resolve_phone_target(db, case_id, "phone_thread", thread_key)
        except link_types.LinkTargetError as exc:
            raise ReviewMarkError(str(exc)) from exc
        total = conn.execute(text(
            "SELECT event_count FROM pv_thread WHERE case_id = :c AND thread_key = :k"),
            {"c": case_id, "k": thread_key}).scalar() or 0
        anchor = link_types.phone_anchor(target, None)
    now = datetime.now(timezone.utc).isoformat()
    review = {"reviewed_by": str(user.id), "reviewed_by_name": user.name or user.email, "reviewed_at": now,
              "record_count": int(total), "scope": scope or {}, "position": position}
    tid = _task_id(conn, case_id, user.id, create=True)
    row = conn.execute(text(
        "SELECT id, source_anchor FROM case_task_links WHERE task_id = :t AND target_type = 'phone_thread' AND "
        "target_id = :k"), {"t": tid, "k": thread_key}).first()
    import json
    if row:
        old = row.source_anchor if isinstance(row.source_anchor, dict) else {}
        earlier = list(old.get("earlier") or [])
        if old.get("reviewed_at"):
            earlier.append({k: old.get(k) for k in ("reviewed_by", "reviewed_by_name", "reviewed_at", "record_count",
                                                     "scope", "position")})
        new = {**old, **review, "earlier": earlier}
        conn.execute(text("UPDATE case_task_links SET source_anchor = CAST(:a AS jsonb), updated_at = now() "
                          "WHERE id = :i"), {"a": json.dumps(new), "i": row.id})
    else:
        new = {**anchor, **review, "earlier": []}
        conn.execute(text(
            "INSERT INTO case_task_links (id, task_id, case_id, target_type, target_id, label, source_anchor, "
            "created_by_user_id, created_at, updated_at) VALUES (:i, :t, :c, 'phone_thread', :k, :l, "
            "CAST(:a AS jsonb), :u, now(), now())"),
            {"i": uuid.uuid4(), "t": tid, "c": case_id, "k": thread_key, "l": "Reviewed", "a": json.dumps(new),
             "u": user.id})
    system_log_service.log(log_type=LogType.CASE_OPERATION, origin=LogOrigin.BACKEND,
                           action="Marked a phone conversation reviewed",
                           details={"case_id": str(case_id), "thread_key": thread_key, "record_count": int(total)},
                           user=user.email, success=True, db=db)
    db.commit()
    return review_words(new, total)


def undo(db, case_id, thread_key: str, user) -> dict | None:
    """Remove the latest mark on a thread; the one before it, if any, becomes current again."""
    from services.system_log_service import LogOrigin, LogType, system_log_service
    import json
    conn = db.connection()
    tid = _task_id(conn, case_id, user.id, create=False)
    row = tid and conn.execute(text(
        "SELECT id, source_anchor FROM case_task_links WHERE task_id = :t AND target_type = 'phone_thread' AND "
        "target_id = :k"), {"t": tid, "k": thread_key}).first()
    if not row and tid:  # a mark carried from the replaced report's thread is undone where it was made
        origin = (marks(conn, case_id).get(thread_key) or {}).get("carried_from")
        row = origin and conn.execute(text(
            "SELECT id, source_anchor FROM case_task_links WHERE task_id = :t AND target_type = 'phone_thread' AND "
            "target_id = :k"), {"t": tid, "k": origin}).first()
    if not row:
        raise ReviewMarkError("This conversation has no review mark.")
    old = row.source_anchor if isinstance(row.source_anchor, dict) else {}
    earlier = list(old.get("earlier") or [])
    if earlier:
        prev = earlier.pop()
        new = {**old, **prev, "earlier": earlier}
        conn.execute(text("UPDATE case_task_links SET source_anchor = CAST(:a AS jsonb), updated_at = now() "
                          "WHERE id = :i"), {"a": json.dumps(new), "i": row.id})
    else:
        new = None
        conn.execute(text("DELETE FROM case_task_links WHERE id = :i"), {"i": row.id})
    system_log_service.log(log_type=LogType.CASE_OPERATION, origin=LogOrigin.BACKEND,
                           action="Undid a phone conversation review mark",
                           details={"case_id": str(case_id), "thread_key": thread_key}, user=user.email,
                           success=True, db=db)
    db.commit()
    return new
