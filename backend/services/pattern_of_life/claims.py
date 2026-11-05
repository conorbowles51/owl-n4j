"""Statement claims (04 sections 9.1 and 9.2, unit U11).

A claim is a statement to test against the phones: a kind, a subject, a window and the statement's own words. It is
``draft`` until a named person confirms it, and only a confirmed claim is evaluated. Every version is copied to
``pol_claim_revision``; an edit names the version it was made on and is refused (409) when someone else changed the
claim first. Editing a confirmed claim returns it to draft, because the confirmation was of the earlier words.

A drafted claim (``origin = 'ai_draft'``) carries the model that drafted it and the Workspace AI output it came from,
and reads "Drafted by <model>, not confirmed" until a person confirms it. The model never sets an instant: a draft
has no window until a person sets one.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from services.pattern_of_life import subjects

KINDS = ("inactive", "active", "at_place", "not_at_place", "with_subject", "apart_from_subject", "no_contact",
         "contact")
PLACE_KINDS = ("at_place", "not_at_place")
SUBJECT_KINDS = ("with_subject", "apart_from_subject")
CONTACT_KINDS = ("no_contact", "contact")
EDITABLE = ("kind", "subject", "window_start", "window_end", "window_zone", "window_text", "place", "activity",
            "counterpart", "source_anchor")
MAX_WINDOW_DAYS = 31
STATUS_WORDS = {"draft": "Not confirmed", "confirmed": "Confirmed", "withdrawn": "Withdrawn"}


class ClaimError(ValueError):
    def __init__(self, message, status=400, fields=None):
        super().__init__(message)
        self.status = status
        self.fields = fields or []


def _instant(v, name):
    if v is None or isinstance(v, datetime):
        dt = v
    else:
        try:
            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except ValueError:
            raise ClaimError("%s must be a date and time with its offset." % name, fields=[name])
    if dt is not None and dt.tzinfo is None:
        raise ClaimError("%s must carry its offset (or Z)." % name, fields=[name])
    return dt


def _place_ok(place) -> bool:
    if not isinstance(place, dict):
        return False
    try:
        lat, lon, r = float(place["lat"]), float(place["lon"]), float(place["radius_m"])
    except (KeyError, TypeError, ValueError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180 and 0 < r <= 50000


def _check_shape(conn, case_id, c):
    """Field rules that hold for a draft too (a draft may be incomplete, never malformed)."""
    if c.get("kind") not in KINDS:
        raise ClaimError("The kind is one of: %s." % ", ".join(KINDS), fields=["kind"])
    try:
        subjects.resolve(conn, case_id, c.get("subject"))
    except subjects.SubjectError as exc:
        raise ClaimError(str(exc), exc.status, fields=["subject"])
    a, b = _instant(c.get("window_start"), "window_start"), _instant(c.get("window_end"), "window_end")
    if a and b:
        if b <= a:
            raise ClaimError("The window must end after it starts.", fields=["window_end"])
        if (b - a).days > MAX_WINDOW_DAYS:
            raise ClaimError("A window is at most %d days." % MAX_WINDOW_DAYS, fields=["window_end"])
    place = c.get("place")
    if place is not None and not isinstance(place, dict):
        raise ClaimError("A place is a point and radius, a routine place, or the words of the statement.",
                         fields=["place"])
    if isinstance(place, dict) and any(k in place for k in ("lat", "lon", "radius_m")) and not _place_ok(place):
        raise ClaimError("A place needs a latitude, a longitude and a radius from 1 m to 50,000 m.", fields=["place"])
    cp = c.get("counterpart")
    if cp is not None and c["kind"] in SUBJECT_KINDS:
        try:
            subjects.resolve(conn, case_id, cp)
        except subjects.SubjectError as exc:
            raise ClaimError("The other person: %s" % exc, exc.status, fields=["counterpart"])
    if cp is not None and c["kind"] in CONTACT_KINDS:
        if isinstance(cp, dict) and cp.get("kind") == "dossier":
            try:
                subjects.resolve(conn, case_id, cp)
            except subjects.SubjectError as exc:
                raise ClaimError("The other person: %s" % exc, exc.status, fields=["counterpart"])
        elif isinstance(cp, dict) and isinstance(cp.get("identity_ids"), list) and cp["identity_ids"]:
            ids = [str(x) for x in cp["identity_ids"]]
            n = conn.execute(text("SELECT count(*) FROM phone_identities WHERE case_id = :c AND id = ANY(CAST(:i AS "
                                  "uuid[]))"), {"c": case_id, "i": ids}).scalar()
            if n != len(set(ids)):
                raise ClaimError("An identity in the claim is not in this case.", 404, fields=["counterpart"])
        else:
            raise ClaimError("The other side is a person (dossier) or a list of identities.", fields=["counterpart"])
    act = c.get("activity")
    if act is not None:
        if not isinstance(act, dict):
            raise ClaimError("Activity is a small set of options.", fields=["activity"])
        tol = act.get("tolerance_minutes", 0)
        if not isinstance(tol, int) or tol < 0 or tol > 120:
            raise ClaimError("The tolerance is whole minutes from 0 to 120.", fields=["activity"])


def missing_for_confirm(c) -> list:
    """The fields a person still has to settle before the claim can be confirmed (422 lists them)."""
    out = []
    if not c.get("window_start"):
        out.append("window_start")
    if not c.get("window_end"):
        out.append("window_end")
    if not c.get("window_zone"):
        out.append("window_zone")
    if c["kind"] in PLACE_KINDS and not _place_ok(c.get("place")):
        out.append("place")  # a place given as words must be resolved to a point first (9.1)
    if c["kind"] in SUBJECT_KINDS + CONTACT_KINDS and not c.get("counterpart"):
        out.append("counterpart")
    return out


def _snapshot(row) -> dict:
    keys = ("id", "version", "status", "kind", "subject", "window_start", "window_end", "window_zone", "window_text",
            "place", "activity", "counterpart", "origin", "source_anchor", "ai_output_id", "ai_model",
            "confirmed_by_name", "confirmed_at", "withdrawn_reason")
    return json.loads(json.dumps({k: row[k] for k in keys}, default=str))


def _revise(conn, claim_id, change, actor):
    row = get(conn, None, claim_id, raw=True)
    conn.execute(text(
        "INSERT INTO pol_claim_revision (claim_id, version, snapshot, changed_by_name, changed_by_user_id, change) "
        "VALUES (:c, :v, CAST(:s AS jsonb), :n, :u, :ch)"),
        {"c": claim_id, "v": row["version"], "s": json.dumps(_snapshot(row)), "n": actor.name,
         "u": actor.user_id, "ch": change})


def _j(v):
    return None if v is None else json.dumps(v)


def create(conn, case_id, fields: dict, actor, *, origin="manual", ai_output_id=None, ai_model=None) -> dict:
    c = {k: fields.get(k) for k in EDITABLE}
    if origin == "ai_draft":
        # the model never sets an instant (9.2 step 3): a drafted claim has no window until a person sets one
        if c.get("window_start") or c.get("window_end"):
            raise ClaimError("A drafted claim cannot carry a time; a person sets the window.", fields=["window_start"])
        if not ai_output_id:
            raise ClaimError("A drafted claim names the AI output it came from.")
    _check_shape(conn, case_id, c)
    cid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO pol_claim (id, case_id, status, kind, subject, window_start, window_end, window_zone, window_text, "
        "place, activity, counterpart, origin, source_anchor, ai_output_id, ai_model, created_by_user_id, "
        "created_by_name) VALUES (:i, :case, 'draft', :k, CAST(:s AS jsonb), :a, :b, :z, :t, CAST(:p AS jsonb), "
        "CAST(:ac AS jsonb), CAST(:cp AS jsonb), :o, CAST(:sa AS jsonb), :ai, :am, :u, :n)"),
        {"i": cid, "case": case_id, "k": c["kind"], "s": json.dumps(c["subject"]),
         "a": _instant(c.get("window_start"), "window_start"), "b": _instant(c.get("window_end"), "window_end"),
         "z": c.get("window_zone"), "t": c.get("window_text"), "p": _j(c.get("place")), "ac": _j(c.get("activity")),
         "cp": _j(c.get("counterpart")), "o": origin, "sa": _j(c.get("source_anchor")), "ai": ai_output_id,
         "am": ai_model, "u": actor.user_id, "n": actor.name})
    _revise(conn, cid, "create", actor)
    return get(conn, case_id, cid)


def get(conn, case_id, claim_id, raw=False):
    q = "SELECT * FROM pol_claim WHERE id = :i" + (" AND case_id = :c" if case_id is not None else "")
    row = conn.execute(text(q), {"i": claim_id, "c": case_id}).mappings().first()
    if row is None:
        raise ClaimError("That statement is not in this case.", 404)
    row = dict(row)
    if raw:
        return row
    return view(row, _first_versions(conn, [claim_id]).get(str(claim_id)) if row["origin"] == "ai_draft" else None)


def _as_drafted(snapshot) -> dict:
    """What the model wrote, from the claim's first version: it stays on show however a person edits the claim."""
    anchor = snapshot.get("source_anchor") or {}
    place = snapshot.get("place") or {}
    return {"kind": snapshot.get("kind"), "window_text": snapshot.get("window_text"), "place_text": place.get("text"),
            "counterpart_text": anchor.get("counterpart_text"), "quote": anchor.get("quote")}


def _first_versions(conn, claim_ids) -> dict:
    if not claim_ids:
        return {}
    return {str(r.claim_id): r.snapshot for r in conn.execute(text(
        "SELECT DISTINCT ON (claim_id) claim_id, snapshot FROM pol_claim_revision "
        "WHERE claim_id = ANY(CAST(:i AS uuid[])) ORDER BY claim_id, version"), {"i": [str(x) for x in claim_ids]})}


def view(row, first_version=None) -> dict:
    out = dict(row)
    if first_version is not None:
        out["as_drafted"] = _as_drafted(first_version)
    out["status_words"] = STATUS_WORDS[row["status"]]
    if row["origin"] == "ai_draft" and row["status"] == "draft":
        out["status_words"] = "Drafted by %s, not confirmed" % (row.get("ai_model") or "a model")
    out["missing_for_confirm"] = missing_for_confirm(row) if row["status"] == "draft" else []
    return out


def list_claims(conn, case_id, status=None) -> dict:
    q = "SELECT * FROM pol_claim WHERE case_id = :c" + (" AND status = :s" if status else "")
    rows = [dict(r) for r in conn.execute(text(q + " ORDER BY created_at, id"),
                                          {"c": case_id, "s": status}).mappings()]
    first = _first_versions(conn, [r["id"] for r in rows if r["origin"] == "ai_draft"])
    items = [view(r, first.get(str(r["id"]))) for r in rows]
    return {"total": len(items), "items": items}


def _expect(row, expected_version):
    if row["version"] != expected_version:
        raise ClaimError("Someone else changed this statement while you were looking (it is now version %d). Their "
                         "change is shown; yours was not saved." % row["version"], 409)


def edit(conn, case_id, claim_id, fields: dict, expected_version: int, actor) -> dict:
    row = get(conn, case_id, claim_id, raw=True)
    _expect(row, expected_version)
    if row["status"] == "withdrawn":
        raise ClaimError("A withdrawn statement cannot be edited.", 409)
    unknown = sorted(set(fields) - set(EDITABLE))
    if unknown:
        raise ClaimError("These cannot be edited: %s." % ", ".join(unknown), fields=unknown)
    c = {k: row[k] for k in EDITABLE}
    c.update(fields)
    _check_shape(conn, case_id, c)
    conn.execute(text(
        "UPDATE pol_claim SET version = version + 1, status = 'draft', confirmed_by_user_id = NULL, "
        "confirmed_by_name = NULL, confirmed_at = NULL, kind = :k, subject = CAST(:s AS jsonb), window_start = :a, "
        "window_end = :b, window_zone = :z, window_text = :t, place = CAST(:p AS jsonb), activity = CAST(:ac AS jsonb), "
        "counterpart = CAST(:cp AS jsonb), source_anchor = CAST(:sa AS jsonb), updated_at = clock_timestamp() "
        "WHERE id = :i"),
        {"i": claim_id, "k": c["kind"], "s": json.dumps(c["subject"]),
         "a": _instant(c.get("window_start"), "window_start"), "b": _instant(c.get("window_end"), "window_end"),
         "z": c.get("window_zone"), "t": c.get("window_text"), "p": _j(c.get("place")), "ac": _j(c.get("activity")),
         "cp": _j(c.get("counterpart")), "sa": _j(c.get("source_anchor"))})
    _revise(conn, claim_id, "edit", actor)
    return get(conn, case_id, claim_id)


def confirm(conn, case_id, claim_id, expected_version: int, actor) -> dict:
    """Only a named person confirms. A model's work is never confirmed under a person's name by a model (rule 1)."""
    if actor is None or not getattr(actor, "user_id", None) or getattr(actor, "origin", None):
        raise ClaimError("A statement is confirmed only by a signed-in person.", 403)
    row = get(conn, case_id, claim_id, raw=True)
    _expect(row, expected_version)
    if row["status"] != "draft":
        raise ClaimError("Only a statement that is not yet confirmed can be confirmed.", 409)
    missing = missing_for_confirm(row)
    if missing:
        raise ClaimError("Settle these before confirming: %s." % ", ".join(missing), 422, fields=missing)
    conn.execute(text(
        "UPDATE pol_claim SET version = version + 1, status = 'confirmed', confirmed_by_user_id = :u, "
        "confirmed_by_name = :n, confirmed_at = :t, updated_at = clock_timestamp() WHERE id = :i"),
        {"i": claim_id, "u": actor.user_id, "n": actor.name, "t": datetime.now(timezone.utc)})
    _revise(conn, claim_id, "confirm", actor)
    return get(conn, case_id, claim_id)


def withdraw(conn, case_id, claim_id, reason: str, actor) -> dict:
    if not isinstance(reason, str) or not reason.strip():
        raise ClaimError("Say why the statement is withdrawn.", fields=["reason"])
    row = get(conn, case_id, claim_id, raw=True)
    if row["status"] == "withdrawn":
        raise ClaimError("That statement is already withdrawn.", 409)
    conn.execute(text("UPDATE pol_claim SET version = version + 1, status = 'withdrawn', withdrawn_reason = :r, "
                      "updated_at = clock_timestamp() WHERE id = :i"), {"i": claim_id, "r": reason.strip()})
    _revise(conn, claim_id, "withdraw", actor)
    return get(conn, case_id, claim_id)


def revisions(conn, case_id, claim_id) -> dict:
    get(conn, case_id, claim_id, raw=True)
    rows = [dict(r) for r in conn.execute(text(
        "SELECT version, change, changed_by_name, changed_at, snapshot FROM pol_claim_revision WHERE claim_id = :c "
        "ORDER BY version"), {"c": claim_id}).mappings()]
    return {"total": len(rows), "items": rows}
