"""How this was found (07 J-17): the block every finding that holds phone links shows. Nothing in it is typed.

It is built from the finding's phone links and the case's own records, each time it is asked for:

- **Scope**: the saved selections behind the finding (their words, counts and the searches in their frozen
  filter), the threads, phones and views linked to it.
- **Readings**: every record the finding relies on (linked directly or frozen in a selection), counted by how it
  was read: confirmed by a person (``reviewed``), mapped by the system and not yet confirmed
  (``applied_unconfirmed``), or read as recorded with no mapping (``generic``, ``captured_only``). A record no
  longer in its phone's current reading is counted as such, never dropped.
- **Identity decisions**: each linked identity with the number of person decisions recorded on it.
- **Assumptions** per phone the readings come from, as codes: owner (``owner_confirmed``, ``owner_computed``,
  ``owner_unknown``), clock (``zone_recorded``, ``clock_zone_unknown``; ``clock_offset_unknown`` when the
  readings span two or more phones, 05 section 3.5) and completeness (``counts_reconciled``,
  ``counts_not_reconciled``, ``partly_read``).
- **Label**: "Result for report" only when nothing in it rests on the system alone: no analysis result (an
  analysis is always a lead, 05 section 3), no unconfirmed or missing reading, every linked identity decided by a
  person and every assumption settled. Otherwise "Lead for enquiry", with the reasons.

The counts equal the links and decisions behind it: ``links.total`` is the number of phone links on the finding.
"""
from __future__ import annotations

import json
import uuid
from collections import Counter

from sqlalchemy import text

from postgres import link_types

LEAD, RESULT = "Lead for enquiry", "Result for report"
HEADING = "How this was found"
SETTLED = {"owner_confirmed", "zone_recorded", "counts_reconciled"}
WORDS = {
    "owner_confirmed": "The owner of {p} was confirmed by a person.",
    "owner_computed": "The owner of {p} is the system's reading of the report, not confirmed by a person.",
    "owner_unknown": "No owner is known for {p}.",
    "zone_recorded": "Times on {p} are read in its recorded zone, {z}.",
    "clock_zone_unknown": "The time zone of {p} is not recorded; times are shown as stored.",
    "clock_offset_unknown": "The readings compare times from {n} phones; no estimate of the offset between their "
                            "clocks exists.",
    "counts_reconciled": "Every record of {p} was read and the counts match the report.",
    "counts_not_reconciled": "The records of {p} were read, but the counts were not checked against the report.",
    "partly_read": "{p} was only partly read.",
}


class NotFound(LookupError):
    pass


def _uuid(v):
    try:
        return uuid.UUID(str(v))
    except (TypeError, ValueError, AttributeError):
        return None


def _searches(filter_json):
    try:
        f = filter_json if isinstance(filter_json, dict) else json.loads(filter_json or "{}")
    except ValueError:
        return []
    q = ((f.get("text") or {}).get("query") or "").strip()
    return [{"query": q, "exact": bool((f.get("text") or {}).get("exact_characters"))}] if q else []


def explain(conn, case_id, entry_id) -> dict:
    case, entry = _uuid(case_id), _uuid(entry_id)
    if case is None or entry is None:
        raise NotFound(entry_id)
    row = conn.execute(text(
        "SELECT entry_type FROM workspace_entries WHERE id = :e AND case_id = :c AND deleted_at IS NULL"),
        {"e": entry, "c": case}).first()
    if row is None:
        raise NotFound(entry_id)
    links = conn.execute(text(
        "SELECT id, target_type, target_id, target_label FROM workspace_entry_links WHERE entry_id = :e AND "
        "case_id = :c AND target_type = ANY(:t) ORDER BY target_type, target_id"),
        {"e": entry, "c": case, "t": list(link_types.PHONE_TYPES) + ["statement_check"]}).all()
    out = {"entry_id": str(entry), "entry_type": row.entry_type, "heading": HEADING,
           "has_phone_links": bool(links),
           "links": {"total": len(links), "by_type": dict(Counter(l.target_type for l in links))}}
    if not links:
        return out
    from services.phone.readings import phone_labels
    labels = phone_labels(conn, case)

    by_type = {}
    for l in links:
        by_type.setdefault(l.target_type, []).append(l)
    scope, searches, record_uids, phones = [], [], set(), set()
    for l in by_type.get("phone_selection", []):
        s = conn.execute(text(
            "SELECT words, filter, record_uids, record_count, event_count, mapping_versions FROM phone_selections "
            "WHERE id = :i AND case_id = :c"), {"i": _uuid(l.target_id), "c": case}).first()
        if s is None:
            scope.append({"kind": "selection", "words": l.target_label or "A phone selection", "missing": True})
            continue
        found = _searches(s.filter)
        searches += [x for x in found if x not in searches]
        record_uids.update(str(u) for u in (s.record_uids or []))
        phones.update(p["extraction_id"] for p in (s.mapping_versions or {}).get("phones", []))
        scope.append({"kind": "selection", "words": s.words, "records": int(s.record_count or 0),
                      "events": int(s.event_count or 0), "searches": found})
    for l in by_type.get("phone_thread", []):
        t = conn.execute(text(
            "SELECT extraction_id, event_count FROM phone_threads t JOIN phone_interpretation_state s ON "
            "s.extraction_id = t.extraction_id AND s.generation = t.generation WHERE t.thread_key = :k AND "
            "t.case_id = :c"), {"k": l.target_id, "c": case}).first()
        if t is not None:
            phones.add(str(t.extraction_id))
        scope.append({"kind": "conversation", "words": l.target_label or "A conversation",
                      "events": int(t.event_count or 0) if t else None, "missing": t is None})
    for l in by_type.get("phone_extraction", []):
        phones.add(l.target_id)
        scope.append({"kind": "phone", "words": labels.get(l.target_id) or l.target_label or "A phone"})
    for l in by_type.get("phone_view", []):
        scope.append({"kind": "view", "words": l.target_label or "A saved view"})
    for l in by_type.get("phone_analysis", []) + by_type.get("statement_check", []):
        scope.append({"kind": "analysis", "words": l.target_label or "An analysis result"})
    for l in by_type.get("phone_file", []):
        scope.append({"kind": "file", "words": l.target_label or "A phone file"})
    record_uids.update(l.target_id for l in by_type.get("phone_record", []))

    # readings: the current reading of each record the finding relies on
    levels, found_uids = Counter(), set()
    ids = [u for u in (_uuid(x) for x in record_uids) if u is not None]
    for part in range(0, len(ids), 5000):
        for r in conn.execute(text(
                # a message or call is counted at the level its row shows on screen (the event's reading)
                "SELECT r.record_uid, r.extraction_id, coalesce((SELECT ev.interpretation_level FROM "
                "phone_comm_events ev WHERE ev.record_uid = r.record_uid AND ev.generation = r.generation ORDER BY "
                "ev.interpretation_level = 'applied_unconfirmed' DESC LIMIT 1), r.interpretation_level) AS "
                "interpretation_level FROM phone_record_summaries r JOIN phone_interpretation_state s ON "
                "s.extraction_id = r.extraction_id AND s.generation = r.generation "
                "WHERE r.case_id = :c AND r.record_uid = ANY(:u)"), {"c": case, "u": ids[part:part + 5000]}):
            found_uids.add(str(r.record_uid))
            phones.add(str(r.extraction_id))
            levels[r.interpretation_level] += 1
    readings = {"records": len(record_uids), "confirmed": levels["reviewed"],
                "unconfirmed": levels["applied_unconfirmed"],
                "as_recorded": levels["generic"] + levels["captured_only"],
                "not_in_current_reading": len(record_uids) - len(found_uids)}

    # identity decisions on the linked identities
    idents = []
    for l in by_type.get("phone_identity", []):
        i = conn.execute(text(
            "SELECT i.id, i.value_display, l.dossier_id IS NOT NULL AS linked FROM phone_identities i LEFT JOIN "
            "phone_identity_links l ON l.identity_id = i.id WHERE i.case_id = :c AND i.identity_key = :k"),
            {"c": case, "k": l.target_id}).first()
        n = conn.execute(text(
            "SELECT count(*) FROM adjudications WHERE case_id = :c AND subject_type = 'phone_identity' AND "
            "subject_id = :i"), {"c": case, "i": i.id}).scalar() if i else 0
        idents.append({"identity": (i.value_display if i else None) or l.target_label or l.target_id,
                       "decisions": int(n or 0), "linked_to_person": bool(i and i.linked), "missing": i is None})

    # assumptions per phone
    from services.phone import identities
    assumptions = []
    active = [p for p in sorted(phones) if _uuid(p)]
    for p in active:
        x = conn.execute(text(
            "SELECT state, device_zone, reconciliation_state FROM pv_extraction WHERE case_id = :c AND "
            "extraction_id = :e"), {"c": case, "e": _uuid(p)}).first()
        if x is None:
            continue
        name = labels.get(p) or "this phone"
        o = identities.owner(conn, _uuid(p))
        owner = ("owner_confirmed" if o.get("owner_basis") == "manual" else
                 "owner_computed" if o.get("owner_identity_keys") else "owner_unknown")
        zone = "zone_recorded" if x.device_zone else "clock_zone_unknown"
        whole = ("partly_read" if x.state in ("partial", "failed") or x.reconciliation_state == "failed" else
                 "counts_reconciled" if x.reconciliation_state == "exact" else "counts_not_reconciled")
        for code in (owner, zone, whole):
            assumptions.append({"phone": name, "code": code,
                                "words": WORDS[code].format(p=name, z=x.device_zone or "", n=len(active))})
    if len(active) > 1:
        assumptions.append({"phone": None, "code": "clock_offset_unknown",
                            "words": WORDS["clock_offset_unknown"].format(n=len(active), p="", z="")})

    reasons = []
    if any(s["kind"] == "analysis" for s in scope):
        reasons.append("It holds an analysis result, which points to records to examine.")
    if readings["unconfirmed"]:
        reasons.append("%s %s mapped by the system and not yet confirmed by a person." % (
            "{:,}".format(readings["unconfirmed"]), "reading is" if readings["unconfirmed"] == 1 else "readings are"))
    if readings["not_in_current_reading"]:
        reasons.append("%s linked %s no longer in the phone's current reading." % (
            "{:,}".format(readings["not_in_current_reading"]),
            "record is" if readings["not_in_current_reading"] == 1 else "records are"))
    undecided = sum(1 for i in idents if not i["decisions"])
    if undecided:
        reasons.append("%d linked %s no decision by a person." % (undecided, "identity has" if undecided == 1 else
                                                                   "identities have"))
    unsettled = sum(1 for a in assumptions if a["code"] not in SETTLED)
    if unsettled:
        reasons.append("%d %s not settled." % (unsettled, "assumption is" if unsettled == 1 else "assumptions are"))
    if any(s.get("missing") for s in scope):
        reasons.append("A linked item is no longer in the case's current reading.")
    out.update(scope=scope, searches=searches, readings=readings, identities=idents, assumptions=assumptions,
               label=RESULT if not reasons else LEAD, label_reasons=reasons)
    return out
