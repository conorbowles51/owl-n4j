"""Saved phone views (07 section 6; the ``phone_view`` link type).

``save`` keeps the Conversations filter, the address it was saved from, its sentence and how many messages it listed
then, and makes the Workspace note that holds it (one ``phone_view`` link). ``describe`` re-runs the filter live and
gives the count then and now; a view whose phones include a report since replaced says so, because its filter names
a report the case no longer stands on. ``resolve`` is the link resolver.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from postgres import link_types
from services.phone import streams
from services.phone.filters import StreamFilter

REPLACED = ("This view names a phone report that was replaced in this case, so it now lists less than it did; save "
            "the view again on the report the case stands on")


class ViewError(ValueError):
    pass


def _versions(conn, phones):
    return [dict(r._mapping) for r in conn.execute(text(
        "SELECT st.extraction_id::text AS extraction_id, st.generation, st.mapping_set_id::text AS mapping_set_id, "
        "st.interpreter_version FROM phone_interpretation_state st WHERE st.extraction_id::text = ANY(:p) "
        "ORDER BY 1"), {"p": phones})]


def _phones_of(conn, f: StreamFilter):
    if f.phones:
        return sorted(str(p) for p in f.phones)
    return sorted(str(r[0]) for r in conn.execute(text(
        "SELECT e.id FROM phone_extractions e WHERE e.case_id = CAST(:c AS uuid) AND e.standing = 'active'"),
        {"c": f.case_id}))


def save(db, f: StreamFilter, user, *, location: str, words: str, title: str | None = None) -> dict:
    """Store the view and the Workspace note that holds it, in one transaction."""
    from services.workspace_entry_service import create_entry
    if not location.startswith("/cases/%s/" % f.case_id):
        raise ViewError("A view is saved from a screen of this case.")
    conn = db.connection()
    n = streams.shown_count(conn, f)
    vid = uuid.uuid4()
    words = words.strip() or "A phone view"
    conn.execute(text(
        "INSERT INTO phone_views (id, case_id, filter, location, words, event_count, mapping_versions, "
        "created_by_user_id) VALUES (:i, :c, CAST(:f AS jsonb), :l, :w, :n, CAST(:v AS jsonb), :u)"),
        {"i": vid, "c": f.case_id, "f": f.model_dump_json(), "l": location, "w": words, "n": n,
         "v": json.dumps({"phones": _versions(conn, _phones_of(conn, f))}), "u": getattr(user, "id", None)})
    body = ("Saved view: %s. It listed %s %s when saved; opening it lists what the filter matches now and says "
            "both counts." % (words, "{:,}".format(n), "message" if n == 1 else "messages"))
    entry = create_entry(db, case_id=uuid.UUID(str(f.case_id)), current_user=user, entry_type="note", body=body,
                         title=(title or "").strip() or "Saved view: %s" % words[:150],
                         links=[{"target_type": "phone_view", "target_id": str(vid), "target_label": words,
                                 "source_anchor": {"origin": "save_this_view"}}])
    return {"id": str(vid), "entry_id": str(entry["id"]), "event_count": n, "words": words}


def _row(conn, case_id, view_id):
    try:
        vid, case = uuid.UUID(str(view_id)), uuid.UUID(str(case_id))
    except (TypeError, ValueError, AttributeError):
        return None
    return conn.execute(text(
        "SELECT id, filter, location, words, event_count, mapping_versions, created_at FROM phone_views WHERE id = :i "
        "AND case_id = :c"), {"i": vid, "c": case}).first()


def _replaced(conn, case_id, row) -> bool:
    phones = [p["extraction_id"] for p in (row.mapping_versions or {}).get("phones", [])]
    if not phones:
        return False
    active = conn.execute(text(
        "SELECT count(*) FROM phone_extractions e WHERE e.case_id = CAST(:c AS uuid) AND e.standing = 'active' AND "
        "e.id::text = ANY(:p)"), {"c": str(case_id), "p": phones}).scalar()
    return active != len(phones)


def describe(db, case_id, view_id) -> dict | None:
    """The saved view re-run live: the count when saved and now, and where it opens."""
    conn = db.connection()
    row = _row(conn, case_id, view_id)
    if row is None:
        return None
    f = StreamFilter.model_validate(row.filter)
    now = streams.shown_count(conn, f)
    then = int(row.event_count)
    when = row.created_at.strftime("%B %-d, %Y") if row.created_at else "a date not recorded"
    noun = lambda k: "message" if k == 1 else "messages"  # noqa: E731
    words = "Saved view \"%s\": %s %s when saved on %s; %s now." % (row.words, "{:,}".format(then), noun(then), when,
                                                         "{:,}".format(now))
    return {"id": str(row.id), "words": row.words, "location": row.location, "filter": row.filter,
            "event_count_then": then, "event_count_now": now,
            "created_at": row.created_at.isoformat() if row.created_at else None, "sentence": words,
            "replaced": REPLACED if _replaced(conn, case_id, row) else None}


def resolve(db, case_id, target_id):
    row = _row(db.connection(), case_id, target_id)
    if row is None:
        return None
    if _replaced(db.connection(), case_id, row):
        raise link_types.LinkTargetError(REPLACED)
    return link_types.PhoneTarget(label=row.words, mapping_versions=dict(row.mapping_versions or {}),
                                  metadata={"event_count": int(row.event_count)})
