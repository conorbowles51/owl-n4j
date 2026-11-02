"""Key dates and case terms (04 section 8.6; 07 section 5 "entered once per case and reused by every analysis").

Each is a Workspace note tagged ``key date`` or ``case term`` (so it shows, is searched and is deleted with the rest
of the Workspace) plus a ``pol_key_date`` marker holding what the analyses read: the instant and the zone it was
given in, or the term. The note and the marker are written in one transaction. A deleted note's key date is not
offered.
"""
from __future__ import annotations

import uuid
from datetime import timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text

TAGS = {"date": "key date", "term": "case term"}


class KeyDateError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _zone(name):
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        raise KeyDateError("Unknown time zone %s." % name)


def create(db, case_id, user, *, kind, label, instant=None, zone=None, term=None, note=None) -> dict:
    from services.workspace_entry_service import create_entry
    label = (label or "").strip()
    if not label:
        raise KeyDateError("Give the key date or term a name.")
    if kind == "date":
        if instant is None or instant.tzinfo is None or not zone:
            raise KeyDateError("A key date needs an instant with its offset and the zone it was given in.")
        z = _zone(zone)
        local = instant.astimezone(z)
        body = "%s: %s (%s). %s" % (label, local.strftime("%Y-%m-%d %H:%M"), zone, note or "")
        title = "Key date: %s" % label
    elif kind == "term":
        term = (term or "").strip()
        if not term:
            raise KeyDateError("A case term needs its words.")
        body = "%s: \"%s\". %s" % (label, term, note or "")
        title = "Case term: %s" % label
    else:
        raise KeyDateError("A key date is a date or a term.")
    eid = uuid.uuid4()
    db.execute(text(
        "INSERT INTO pol_key_date (entry_id, case_id, kind, label, instant_utc, zone, term) VALUES "
        "(:e, :c, :k, :l, :i, :z, :t)"),
        {"e": eid, "c": case_id, "k": kind, "l": label[:240],
         "i": instant.astimezone(timezone.utc) if kind == "date" else None,
         "z": zone if kind == "date" else None, "t": term if kind == "term" else None})
    create_entry(db, case_id=case_id, current_user=user, entry_id=eid, entry_type="note", body=body.strip(),
                 title=title[:240], tags=[TAGS[kind]])  # commits the note and the marker together
    return get(db.connection(), case_id, eid)


def _row(r) -> dict:
    out = {"entry_id": str(r["entry_id"]), "kind": r["kind"], "label": r["label"], "zone": r["zone"],
           "term": r["term"], "instant_utc": r["instant_utc"], "local": None, "title": r["title"]}
    if r["instant_utc"] is not None:
        out["local"] = r["instant_utc"].astimezone(ZoneInfo(r["zone"])).isoformat()
    return out


_SELECT = ("SELECT k.entry_id, k.kind, k.label, k.instant_utc, k.zone, k.term, w.title FROM pol_key_date k "
           "JOIN workspace_entries w ON w.id = k.entry_id WHERE k.case_id = :c AND w.deleted_at IS NULL")


def get(conn, case_id, entry_id) -> dict | None:
    r = conn.execute(text(_SELECT + " AND k.entry_id = :e"), {"c": case_id, "e": entry_id}).mappings().first()
    return _row(r) if r else None


def list_for_case(conn, case_id, kind=None) -> dict:
    """Every key date and case term of the case, dates in time order. Analyses in 05 read this."""
    q = _SELECT + (" AND k.kind = :k" if kind else "") + " ORDER BY k.kind, k.instant_utc NULLS LAST, k.label"
    rows = [_row(r) for r in conn.execute(text(q), {"c": case_id, "k": kind}).mappings()]
    return {"total": len(rows), "items": rows}
