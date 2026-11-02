"""Model drafting of statement claims (04 section 9.2, unit U12).

A Workspace AI output of type ``statement_claims`` reads a dossier's selected interviews, or one phone conversation's
text, and drafts the claims the statement makes. It runs under the ``statement_claim_drafting`` workload of the model
policy (DeepSeek by default, through the existing switches) and reads the case's phone material in full, with no
separate case setting (standing decision 8, Neil 2026-11-01 "full phone visibility"). Only material of the case the
request is made in is read.

The model drafts words only: kind, the statement's own words for subject, time, place and the other side, a quote and
the sources it cites. Every claim must cite a supplied source or the output is rejected. The model never sets an
instant: any time field it returns is discarded and counted. Accepting the output creates ``pol_claim`` rows with
``origin = 'ai_draft'`` and ``status = 'draft'`` and no window; a named person sets the window and confirms each.
"""
from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import text

from services.pattern_of_life import claims

WORKLOAD = "statement_claim_drafting"
OUTPUT_TYPE = "statement_claims"
ALLOWED_CLAIM_KEYS = ("kind", "subject_text", "window_text", "place_text", "counterpart_text", "quote", "citation_ids")
MAX_CONVERSATION_ROWS = 2000
MAX_SOURCE_CHARACTERS = 72_000
CHUNK_ROWS = 40
FAILED_WORDS = "AI drafting could not run. Enter claims by hand, or try again."


class DraftingError(ValueError):
    pass


def conversation_sources(db, case_id, thread_key) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """A conversation's text rows, oldest first, in chunks of 40 rows; each chunk is a cited source. The phone's
    current reading only, and only a conversation of this case (404 otherwise)."""
    rows = db.execute(text(
        "SELECT ev.event_uid, ev.record_uid, ev.extraction_id, ev.sort_instant, ev.direction, ev.body, ev.kind "
        "FROM pv_comm_event ev WHERE ev.case_id = :c AND ev.thread_key = :t AND ev.body IS NOT NULL AND "
        "btrim(ev.body) <> '' ORDER BY ev.sort_instant NULLS LAST, ev.event_uid LIMIT :n"),
        {"c": case_id, "t": thread_key, "n": MAX_CONVERSATION_ROWS + 1}).mappings().all()
    if not rows:
        exists = db.execute(text("SELECT 1 FROM pv_thread WHERE case_id = :c AND thread_key = :t"),
                            {"c": case_id, "t": thread_key}).scalar()
        if not exists:
            raise DraftingError("That conversation is not in this case.")
        raise DraftingError("That conversation holds no text to read.")
    total = len(rows)
    rows = rows[:MAX_CONVERSATION_ROWS]
    sources, used = [], 0
    clipped = total > MAX_CONVERSATION_ROWS
    for i in range(0, len(rows), CHUNK_ROWS):
        part = rows[i:i + CHUNK_ROWS]
        body = "\n".join("[%s] %s: %s" % (r["sort_instant"].isoformat() if r["sort_instant"] else "time not recorded",
                                          {"outgoing": "phone's user", "incoming": "other side"}.get(r["direction"],
                                                                                                     "unknown sender"),
                                          r["body"].strip()) for r in part)
        if used + len(body) > MAX_SOURCE_CHARACTERS:
            clipped = True
            break
        used += len(body)
        sid = "S%d" % (len(sources) + 1)
        sources.append({
            "source_id": sid, "evidence_file_id": None, "interview_id": None,
            "filename": "Conversation (%d messages)" % len(part),
            "source_anchor": {"thread_key": thread_key, "event_uids": [str(r["event_uid"]) for r in part],
                              "record_uids": [str(r["record_uid"]) for r in part],
                              "extraction_id": str(part[0]["extraction_id"])},
            "content_hash": hashlib.sha256(body.encode()).hexdigest(), "text": body,
            "url": "/cases/%s/phones?thread=%s" % (case_id, thread_key)})
    read = sum(len(s["source_anchor"]["event_uids"]) for s in sources)
    # every limit is stated: a conversation longer than the bound is read up to it and the draft says so
    return sources, {"conversation_rows_read": read,
                     "conversation_rows_available": total if total <= MAX_CONVERSATION_ROWS else
                     "more than %d" % MAX_CONVERSATION_ROWS, "clipped": clipped}


def prompt(common: str, generation_input: dict) -> str:
    subj = generation_input.get("subject_label") or "the person whose statement this is"
    return common + """
Draft the claims this statement makes that a phone could test, for %s. Kinds: inactive (not using the phone, asleep),
active (using the phone), at_place, not_at_place, with_subject, apart_from_subject, no_contact, contact. Schema:
{"claims": [{"kind": "...", "subject_text": "...", "window_text": "the statement's own words for the time", "place_text": null, "counterpart_text": null, "quote": "the exact words", "citation_ids": ["S1"]}], "limitations": ["..."]}
Use the statement's own words for times and places. Never convert a time into a date or clock value; never give a
start or end time. Every claim cites the source it comes from. Return an empty claims list if the statement makes no
claim a phone could test, and say why in limitations.""" % subj


def validate(content: dict, sources: list[dict]) -> tuple[dict, list[dict]]:
    from services.workspace_ai_service import WorkspaceAIError, _public_source
    if not isinstance(content, dict):
        raise WorkspaceAIError("Generated content must be an object")
    raw = content.get("claims")
    if not isinstance(raw, list):
        raise WorkspaceAIError("claims must be a list")
    lookup = {str(s.get("source_id")): s for s in sources}
    resolved, out, discarded = {}, [], 0
    for c in raw:
        if not isinstance(c, dict):
            raise WorkspaceAIError("Every claim must be an object")
        if c.get("kind") not in claims.KINDS:
            raise WorkspaceAIError("Every claim needs a kind from the list")
        ids = c.get("citation_ids")
        if not isinstance(ids, list) or not ids:
            raise WorkspaceAIError("Every claims item needs at least one source citation")
        uniq = []
        for v in ids:
            sid = str(v).strip()
            src = lookup.get(sid)
            if src is None:
                raise WorkspaceAIError("Unresolved citation: %s" % (sid or "(empty)"))
            if sid not in uniq:
                uniq.append(sid)
                resolved[sid] = _public_source(src) if "text" in src else dict(src)
        if not str(c.get("quote") or "").strip():
            raise WorkspaceAIError("Every claim quotes the statement's words")
        discarded += len([k for k in c if k not in ALLOWED_CLAIM_KEYS])  # a time or anything else outside the schema
        item = {k: (str(c[k]).strip()[:2000] if c.get(k) is not None else None)
                for k in ALLOWED_CLAIM_KEYS if k not in ("citation_ids",)}
        item["citation_ids"] = uniq
        out.append(item)
    lim = content.get("limitations") or []
    if not isinstance(lim, list):
        raise WorkspaceAIError("limitations must be a list")
    if not out and not [x for x in lim if str(x).strip()]:
        raise WorkspaceAIError("A draft with no claims must say why in limitations")
    normalized = {"headline": str(content.get("headline") or "Drafted claims").strip()[:240], "claims": out,
                  "limitations": [str(x).strip() for x in lim if str(x).strip()], "discarded_fields": discarded}
    order = sorted(resolved, key=lambda v: int(v[1:]) if v[1:].isdigit() else 10_000)
    return normalized, [resolved[k] for k in order]


def render(content: dict) -> str:
    lines = [content.get("headline") or "Drafted claims"]
    for c in content.get("claims") or []:
        lines.append("- %s: \"%s\" %s" % (c["kind"], c["quote"], " ".join("[%s]" % s for s in c["citation_ids"])))
    if content.get("limitations"):
        lines += ["", "Limitations"] + ["- %s" % x for x in content["limitations"]]
    return "\n".join(lines)


def proposed_actions(item, content, citations) -> list:
    return [{"action": "create_statement_claims", "claims": len(content.get("claims") or []),
             "content": render(content)}]


def accept(db, item, reviewer) -> list:
    """The drafts become claims: ``ai_draft``, ``draft``, no window, each citing the sources it came from."""
    from services.financial.quarantine_row import actor_from_user
    gi = dict(item.generation_input or {})
    subject = gi.get("subject")
    if not subject:
        raise DraftingError("The draft names no subject to test.")
    model = (item.model_metadata or {}).get("model_id") or "a model"
    by_id = {c["source_id"]: c for c in (item.citations or [])}
    actor = actor_from_user(reviewer)
    conn = db.connection()
    made = []
    for c in (item.content or {}).get("claims") or []:
        anchors = [dict(by_id[s].get("source_anchor") or {}, source_id=s,
                        evidence_file_id=by_id[s].get("evidence_file_id")) for s in c["citation_ids"] if s in by_id]
        fields = {"kind": c["kind"], "subject": subject, "window_text": c.get("window_text"),
                  "place": {"text": c["place_text"]} if c.get("place_text") and c["kind"] in claims.PLACE_KINDS else None,
                  "source_anchor": {"quote": c["quote"], "citations": anchors, "subject_text": c.get("subject_text"),
                                    "counterpart_text": c.get("counterpart_text")}}
        made.append(claims.create(conn, item.case_id, fields, actor, origin="ai_draft", ai_output_id=item.id,
                                  ai_model=model))
    return [{"target_type": "pol_claim", "target_id": str(m["id"])} for m in made]


def check_subject(db, case_id, subject) -> dict:
    from services.pattern_of_life import subjects
    try:
        return subjects.resolve(db.connection(), case_id, subject)
    except subjects.SubjectError as exc:
        raise DraftingError(str(exc))
