"""Mapping proposals in the admin list (02 section 6.8 steps 2, 3 and 5; cb-registry-admin B).

A proposal is a suggested change to a global mapping: a case correction (``correct_phone_reading`` writes one,
``readings.py``) or, later, an AI draft. Nothing here changes the global registry or any mapping: an admin either
rejects a proposal with a reason, or downloads it as a mapping file with ``status: draft`` that a person edits,
reviews and commits (6.8 step 3). The applier never reads ``phone_mapping_proposals`` (6.8 step 2).

Every state change writes a ``phone_mapping_proposal_events`` row before the state changes (the rule of 3.4).
States: ``draft`` -> ``exported`` (first download) or ``rejected``; ``exported`` -> ``rejected``. A rejected
proposal is not downloaded. A second download of an exported proposal changes nothing and writes no event.
"""
from __future__ import annotations

import copy
import datetime as dt
import json

from sqlalchemy import text

STATES = ("draft", "rejected", "exported")
ORIGINS = ("ai_draft", "case_correction")
MAX_LIMIT = 200
MAPPING_PATH = "backend/services/phone/mappings/data/%s/%s.json"


class ProposalRefused(ValueError):
    """``status`` is the HTTP status the router answers with (404, 409 or 422)."""

    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def _event(conn, proposal_id, from_state, to_state, reason, actor_name, actor_email, actor_user_id):
    return conn.execute(text(
        "INSERT INTO phone_mapping_proposal_events (proposal_id, from_state, to_state, reason, actor_name, "
        "actor_email, actor_user_id) VALUES (:p, :fr, :to, :r, :n, :e, :u) RETURNING id"),
        {"p": proposal_id, "fr": from_state, "to": to_state, "r": reason, "n": actor_name, "e": actor_email,
         "u": actor_user_id}).scalar()


def _lock(conn, proposal_id):
    row = conn.execute(text(
        "SELECT id, kind, name, content, origin, decision_id, state, case_id FROM phone_mapping_proposals "
        "WHERE id = :i FOR UPDATE"), {"i": proposal_id}).one_or_none()
    if row is None:
        raise ProposalRefused("Proposal not found.", 404)
    return row


def list_proposals(conn, state=None, origin=None, limit=50, offset=0) -> dict:
    """One page of proposals, newest first, with the total for the filter and the count per state (unfiltered by
    state, filtered by origin) so the page never shows a clipped list as whole."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    where, params = [], {}
    if state:
        where.append("p.state = :s")
        params["s"] = state
    if origin:
        where.append("p.origin = :o")
        params["o"] = origin
    w = (" WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(text("SELECT count(*) FROM phone_mapping_proposals p" + w), params).scalar()
    counts = {s: 0 for s in STATES}
    for s, n in conn.execute(text("SELECT state, count(*) FROM phone_mapping_proposals p%s GROUP BY 1"
                                  % (" WHERE p.origin = :o" if origin else "")), {"o": origin} if origin else {}):
        counts[s] = int(n)
    rows = conn.execute(text(
        "SELECT p.id, p.kind, p.name, p.content, p.model, p.model_version, p.origin, p.decision_id, p.state, "
        "p.case_id, p.created_at, c.title AS case_title, a.actor_name, a.actor_email, a.reason AS decision_reason, "
        "a.created_at AS decided_at, ev.to_state AS last_to, ev.reason AS last_reason, ev.actor_name AS last_actor, "
        "ev.created_at AS last_at "
        "FROM phone_mapping_proposals p LEFT JOIN cases c ON c.id = p.case_id "
        "LEFT JOIN adjudications a ON a.id = p.decision_id "
        "LEFT JOIN LATERAL (SELECT to_state, reason, actor_name, created_at FROM phone_mapping_proposal_events e "
        "WHERE e.proposal_id = p.id ORDER BY e.id DESC LIMIT 1) ev ON true" + w +
        " ORDER BY p.created_at DESC, p.id LIMIT :lim OFFSET :off"), dict(params, lim=limit, off=offset)).fetchall()
    items = []
    for r in rows:
        content = r.content or {}
        items.append({
            "id": str(r.id), "kind": r.kind, "name": r.name, "origin": r.origin, "state": r.state,
            "created_at": r.created_at.isoformat(), "model": r.model, "model_version": r.model_version,
            "case": ({"id": str(r.case_id), "title": r.case_title} if r.case_id else None),
            "rule_id": content.get("rule_id") if r.origin == "case_correction" else None,
            "original": content.get("from") if r.origin == "case_correction" else None,
            "correction": content.get("to") if r.origin == "case_correction" else None,
            "correction_label": content.get("label") if r.origin == "case_correction" else None,
            "decided_by": ({"name": r.actor_name, "email": r.actor_email, "reason": r.decision_reason,
                            "at": r.decided_at.isoformat() if r.decided_at else None} if r.decision_id else None),
            "last_event": ({"to": r.last_to, "reason": r.last_reason, "by": r.last_actor,
                            "at": r.last_at.isoformat()} if r.last_to else None),
            "file_path": MAPPING_PATH % (r.kind, r.name),
        })
    return {"total": int(total), "limit": limit, "offset": offset, "counts": counts, "proposals": items}


def reject(conn, proposal_id, reason, *, actor_name, actor_email=None, actor_user_id=None) -> dict:
    if not (reason or "").strip():
        raise ProposalRefused("A reason is required to reject a proposal.", 422)
    row = _lock(conn, proposal_id)
    if row.state == "rejected":
        raise ProposalRefused("This proposal is already rejected.")
    eid = _event(conn, row.id, row.state, "rejected", reason.strip(), actor_name, actor_email, actor_user_id)
    conn.execute(text("UPDATE phone_mapping_proposals SET state = 'rejected' WHERE id = :i"), {"i": row.id})
    return {"proposal_id": str(row.id), "from": row.state, "to": "rejected", "event_id": eid}


def _apply_correction(content, row_content):
    """The current mapping content with the case correction written in, or None when the rule is not one a
    correction can name (only event time, roles and timestamp-meaning rows offer choices; readings.choices)."""
    rule_id = row_content.get("rule_id") or ""
    to = row_content.get("to")
    body = content.get("body") or {}
    name = content.get("name")
    if content.get("kind") == "type":
        if rule_id == "%s.event_time" % name and isinstance(body.get("event_time"), dict):
            body["event_time"]["field"] = to
            return content
        prefix = "%s.role." % name
        role_map = (body.get("participants") or {}).get("role_map")
        if rule_id.startswith(prefix) and isinstance(role_map, dict) and rule_id[len(prefix):] in role_map:
            role_map[rule_id[len(prefix):]] = to
            return content
        return None
    prefix = "%s/%s/" % (content.get("kind"), name)
    for r in body.get("rows") or []:
        if rule_id == prefix + str(r.get("row_id")) and isinstance(to, dict):
            r["outputs"] = to
            return content
    return None


def build_file(conn, row) -> dict:
    """The mapping file a person edits and commits (6.8 steps 2 and 3): ``status: draft`` (never applied),
    ``origin: human`` for a case correction, no reviewer, version one above the highest recorded."""
    from services.phone.mappings import loader
    pc = row.content or {}
    if row.origin == "ai_draft":
        content = copy.deepcopy(pc)
    else:
        base = conn.execute(text("SELECT content FROM phone_mapping_versions WHERE id::text = :v"),
                            {"v": str(pc.get("mapping_version_id"))}).scalar()
        if base is None:
            raise ProposalRefused("The mapping version this correction was made on is not recorded, so no file can "
                                  "be written from it.")
        content = _apply_correction(copy.deepcopy(base), pc)
        if content is None:
            raise ProposalRefused("This correction names a rule the file cannot express automatically (%s); the "
                                  "original and corrected readings are shown in the list."
                                  % (pc.get("rule_id") or "no rule"))
        content["origin"] = "human"
    top = conn.execute(text("SELECT max(version) FROM phone_mapping_versions WHERE kind = :k AND name = :n"),
                       {"k": row.kind, "n": row.name}).scalar() or 0
    content["version"] = max(int(content.get("version") or 0), int(top)) + 1
    content["status"] = "draft"
    review = dict(content.get("review") or {})
    review["reviewed_by"] = None
    review["reviewed_on"] = None
    review["basis"] = ("Draft from mapping proposal %s (%s%s), downloaded %s. Before committing: check each named "
                       "field against the registry and the coverage counts on at least one phone, write the review "
                       "block and set status to reviewed (02 section 6.8 step 3)."
                       % (row.id, row.origin, (", decision %s" % row.decision_id) if row.decision_id else "",
                          dt.date.today().isoformat()))
    review.setdefault("registry_requirements", [])
    content["review"] = review
    try:
        loader.Envelope.model_validate(content)
    except Exception as exc:  # the file must at least parse as a mapping envelope
        raise ProposalRefused("The file built from this proposal is not a valid mapping: %s" % exc, 422)
    return content


def export(conn, proposal_id, *, actor_name, actor_email=None, actor_user_id=None) -> dict:
    """The file, and ``exported`` recorded on the first download (event first)."""
    row = _lock(conn, proposal_id)
    if row.state == "rejected":
        raise ProposalRefused("A rejected proposal is not downloaded.")
    content = build_file(conn, row)
    event_id = None
    if row.state == "draft":
        event_id = _event(conn, row.id, "draft", "exported", "Downloaded as a mapping file for review", actor_name,
                          actor_email, actor_user_id)
        conn.execute(text("UPDATE phone_mapping_proposals SET state = 'exported' WHERE id = :i"), {"i": row.id})
    return {"filename": "%s.json" % row.name, "path": MAPPING_PATH % (row.kind, row.name), "event_id": event_id,
            "text": json.dumps(content, indent=1, ensure_ascii=False, sort_keys=False) + "\n"}
