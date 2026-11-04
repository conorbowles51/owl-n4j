"""The system's readings and the people who check them (docs/cellebrite/02 sections 6.8, 6.10, 8.8; 07 J-8).

A reading is one judgement call: one rule of one mapping version on one phone (``phone_mapping_judgements``). This
module lists them for a case as plain sentences, draws the examples a person views before deciding, and records
the decision through ``decisions.record`` with the corrections feed (``services.manual_changes``) in the same
transaction:

- ``confirm_phone_reading`` stores the standard reason "Confirmed on the review screen after viewing N examples
  across K kinds" (``reason_kind = standard``), the examples shown and whether each was opened. Looks right is
  refused until every kind was opened (RQ-2, RQ-8).
- ``correct_phone_reading`` takes a choice from a closed list per rule part and a typed reason; it applies to this
  phone in this case, or by explicit choice to the case's phones with the same report format. It writes a
  ``case_correction`` proposal for the admin list. Nothing global changes (6.8 step 6).

Both are case-scoped decisions on (case, extraction, rule, mapping version). The applier reads them through
``apply.register_reading_decisions`` and the sweep re-derives the extraction because its decision revision
changed; rows already written take the confirmed level at once.
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import text

from services.phone.mappings import apply

READING_DECISIONS = ("confirm_phone_reading", "correct_phone_reading")
# Decisions on a phone that change what interpretation derives (5.7): a new one re-derives the phone.
DERIVING_DECISIONS = READING_DECISIONS + ("set_phone_default_region", "set_phone_device_zone", "set_phone_clock_offset",
                                          "apply_phone_zone_to_offsetless")
MAX_APP_KINDS = 6


class ReadingError(ValueError):
    status = 422


class Conflict(ReadingError):
    status = 409


class NotFound(ReadingError):
    status = 404


# ---- labels and words ------------------------------------------------------------------------------------------

LABEL_TOKEN = re.compile(r"(?:^|[_ ])(C\d+)(?=[_ ]|$)")


def label_from_name(path):
    """The ``C<digits>`` token delimited by ``_`` or a space in the report's file name (02 section 12.3), or None."""
    stem = os.path.splitext(os.path.basename((path or "").replace("\\", "/")))[0]
    m = LABEL_TOKEN.search(stem)
    return m.group(1) if m else None


def phone_labels(conn, case_id) -> dict:
    """``{extraction_id: label}`` (02 section 12.3): the label a person set (``set_phone_label``), else the token in
    the report's file name, else ``Phone <n>`` in capture order. A label two phones share carries ``(report k of
    n)`` in capture order, so a sentence naming one phone never names two."""
    rows = conn.execute(text(
        "SELECT e.id, d.path FROM phone_extractions e LEFT JOIN phone_extraction_documents d ON d.extraction_id = e.id "
        "AND d.document_index = 0 WHERE e.case_id = :c ORDER BY e.created_at, e.id"), {"c": case_id}).fetchall()
    out, unnamed = {}, 0
    for e, path in rows:
        label = label_from_name(path)
        if label is None:
            unnamed += 1
            label = "Phone %d" % unnamed
        out[str(e)] = label
    for subject, after in conn.execute(text(
            "SELECT subject_id, after FROM adjudications WHERE case_id = :c AND subject_type = 'phone_extraction' AND "
            "decision = 'set_phone_label' ORDER BY subject_sequence"), {"c": case_id}):
        if str(subject) in out and (after or {}).get("label"):
            out[str(subject)] = after["label"]
    shared = defaultdict(list)
    for e, _ in rows:
        shared[out[str(e)]].append(str(e))
    for label, exts in shared.items():
        if len(exts) > 1:
            for k, e in enumerate(exts, 1):
                out[e] = "%s (report %d of %d)" % (label, k, len(exts))
    return out


def plural(words):
    if words.endswith("s"):
        return words
    if words.endswith("y") and words[-2:-1] not in "aeiou":
        return words[:-1] + "ies"
    return words + "s"


def _phrase(summary, type_words):
    """"In each call, the party marked from is the caller." -> "the party marked from is the caller"."""
    s = (summary or "").strip().rstrip(".")
    s = re.sub(r"^(In|When) each %s,\s*" % re.escape(type_words), "", s, flags=re.I)
    return s[:1].lower() + s[1:]


def sentence(label, type_name, summary, n):
    tw = apply.words(type_name)
    return "On %s, %s: %s. Affects %s %s." % (label, plural(tw), _phrase(summary, tw), "{:,}".format(n),
                                              plural(tw) if n != 1 else tw)


# ---- the queue -------------------------------------------------------------------------------------------------

def queue(conn, case_id, include_resolved=True) -> dict:
    """The readings of a case's active phones at their current generation, grouped by phone and type, most records
    first (07 J-8 step 1)."""
    labels = phone_labels(conn, case_id)
    rows = conn.execute(text(
        "SELECT j.id, j.extraction_id, j.rule_id, j.rule_part, j.type_name, j.summary, j.records_touched, j.status, "
        "j.resolved_by, j.resolved_at, j.resolution_reason, j.adjudication_id, j.mapping_version_id, j.mapping_kind, "
        "j.mapping_name, a.reason_kind, a.after FROM phone_mapping_judgements j "
        "JOIN phone_interpretation_state s ON s.extraction_id = j.extraction_id AND s.generation = j.generation "
        "JOIN phone_extractions e ON e.id = j.extraction_id AND e.standing = 'active' "
        "LEFT JOIN adjudications a ON a.id = j.adjudication_id "
        "WHERE j.case_id = :c AND j.records_touched > 0" + ("" if include_resolved else " AND j.status = 'open'") +
        " ORDER BY j.records_touched DESC, j.rule_id"), {"c": case_id}).fetchall()
    items = []
    for r in rows:
        label = labels.get(str(r.extraction_id), "Phone")
        items.append({
            "id": str(r.id), "extraction_id": str(r.extraction_id), "phone": label, "type_name": r.type_name,
            "type_words": plural(apply.words(r.type_name)), "rule_id": r.rule_id, "part": r.rule_part,
            "sentence": sentence(label, r.type_name, r.summary, int(r.records_touched)),
            "records": int(r.records_touched), "status": r.status,
            "origin": "Mapped by the system, not yet confirmed" if r.status == "open" else None,
            "resolved_by": r.resolved_by, "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            "reason": r.resolution_reason, "reason_kind": r.reason_kind,
            "note": (r.after or {}).get("note") if r.after else None,
            "choices": [{"id": c["id"], "label": c["label"]} for c in choices(conn, r)],
        })
    open_n = sum(1 for i in items if i["status"] == "open")
    return {"case_id": str(case_id), "total": len(items), "open": open_n, "checked": len(items) - open_n,
            "items": items}


def _call(conn, case_id, judgement_id, lock=False):
    r = conn.execute(text(
        "SELECT j.*, e.standing::text AS standing, s.generation AS current_generation FROM phone_mapping_judgements j "
        "JOIN phone_extractions e ON e.id = j.extraction_id LEFT JOIN phone_interpretation_state s ON "
        "s.extraction_id = j.extraction_id WHERE j.id = :j AND j.case_id = :c" + (" FOR UPDATE OF j" if lock else "")),
        {"j": judgement_id, "c": case_id}).one_or_none()
    if r is None:
        raise NotFound("This reading is not in this case.")
    return r


# ---- choices (a closed list per rule part, 6.8 step 8) -----------------------------------------------------------

OTHER_SIDE = {"sender": ("recipient", "The sender is the other party"),
              "recipient": ("sender", "The recipient is the other party"),
              "caller": ("callee", "The caller is the other party"),
              "callee": ("caller", "The callee is the other party")}


def choices(conn, call) -> list:
    part, ev = call.rule_part, None
    if part == "role":
        role = _evidence(conn, call).get("choice")
        out = []
        if role in OTHER_SIDE:
            out.append({"id": "role:" + OTHER_SIDE[role][0], "label": OTHER_SIDE[role][1], "choice": OTHER_SIDE[role][0]})
        out.append({"id": "role:unknown", "label": "Which side this party is on is not known", "choice": "unknown"})
        return out
    if part == "event_time":
        ev = _evidence(conn, call)
        current = ev.get("choice")
        fields = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT f.field_name FROM phone_schema_observations o JOIN phone_schema_fields f ON "
            "f.id = o.registry_id WHERE o.extraction_id = :e AND o.registry_table = 'fields' AND f.type_name = :t AND "
            "f.value_type = 'TimeStamp' AND f.field_kind = 'field' AND o.value_count > 0 ORDER BY 1"),
            {"e": call.extraction_id, "t": call.type_name})]
        return [{"id": "field:" + f, "label": "When it happened is its %s" % apply.words(f), "choice": f}
                for f in fields if f != current]
    if part == "meaning":
        ev = _evidence(conn, call)
        outputs = (ev.get("row") or {}).get("outputs") or {}
        cur = outputs.get("semantics")
        return [{"id": "semantics:" + k, "label": "This time is %s" % w, "choice": dict(outputs, semantics=k)}
                for k, w in apply.SEMANTICS_WORDS.items() if k != cur]
    return []


def _evidence(conn, call):
    ev = call.evidence if hasattr(call, "evidence") else None
    if ev is None:
        ev = conn.execute(text("SELECT evidence FROM phone_mapping_judgements WHERE id = :j"), {"j": call.id}).scalar()
    return ev or {}


# ---- examples (07 J-8 step 2) ----------------------------------------------------------------------------------

PART_SOURCE = {
    "event_time": ("phone_time_values", "mapping_row_id"), "end_time": ("phone_comm_events", "mapping_row_id"),
    "role": ("phone_participations", "mapping_row_id"), "owner_implicit": ("phone_participations", "mapping_row_id"),
    "text": ("phone_texts", "mapping_row_id"), "record": ("phone_record_summaries", "mapping_row_id"),
    "thread": ("phone_comm_events", "mapping_row_id"), "meaning": ("phone_time_values", "meaning_mapping_row_id"),
}


def examples(conn, case_id, judgement_id) -> dict:
    """One example per kind present in the whole affected set: each direction, one to one or group, each app (the
    most frequent six), and the edge cases (no text, no time, deleted on the phone). Examples are drawn across the
    set by a hash of the record id, never the first rows."""
    call = _call(conn, case_id, judgement_id)
    table, col = PART_SOURCE.get(call.rule_part, ("phone_record_summaries", "mapping_row_id"))
    params = {"e": call.extraction_id, "g": call.current_generation, "r": call.rule_id, "c": case_id}
    extra = " AND x.mapping_version_id = :mv" if col == "mapping_row_id" else " AND x.meaning_mapping_version_id = :mv"
    params["mv"] = call.mapping_version_id
    rule_filter = " AND x." + col + " = :r"
    if call.rule_part in ("end_time", "thread"):  # every comm event of the mapping carries the rule
        rule_filter = ""
    if table == "phone_comm_events":
        root = "x.record_uid"
    else:
        root = "coalesce(x.root_record_uid, x.record_uid)"
    rows = conn.execute(text(
        "WITH affected AS (SELECT DISTINCT " + root + " AS r FROM " + table + " x WHERE x.case_id = :c AND "
        "x.extraction_id = :e AND x.generation = :g" + rule_filter + extra + ") "
        "SELECT a.r, md5(a.r::text) AS h, ev.direction, ev.app, th.thread_kind, th.chat_type, "
        "cardinality(th.party_identity_keys) AS parties, (ev.record_uid IS NOT NULL) AS is_event, "
        "(ev.record_uid IS NOT NULL AND coalesce(ev.body, '') = '' AND ev.kind IN ('message', 'email')) AS no_text, "
        "coalesce(ev.sort_instant IS NULL, NOT rs.has_time) AS no_time, coalesce(rs.deleted_state, '') AS deleted_state, "
        "rs.model_type FROM affected a "
        "LEFT JOIN phone_comm_events ev ON ev.record_uid = a.r AND ev.generation = :g "
        "LEFT JOIN phone_threads th ON th.thread_key = ev.thread_key AND th.generation = :g "
        "LEFT JOIN phone_record_summaries rs ON rs.record_uid = a.r AND rs.generation = :g"), params).fetchall()
    kinds = {}

    def add(kid, label, row):
        k = kinds.get(kid)
        if k is None:
            kinds[kid] = {"id": kid, "label": label, "record_uid": str(row.r), "h": row.h, "count": 1}
        else:
            k["count"] += 1
            if row.h < k["h"]:
                k["h"], k["record_uid"] = row.h, str(row.r)

    apps = {}
    for row in rows:
        if row.is_event:
            add("direction:" + row.direction, {"incoming": "Incoming", "outgoing": "Outgoing",
                                               "unknown": "Direction not recorded"}[row.direction], row)
            group = (row.chat_type or "").lower().startswith("group") or (row.parties or 0) > 2
            add("group" if group else "one_to_one", "Group conversation" if group else "One to one", row)
            if row.app:
                apps[row.app] = apps.get(row.app, 0) + 1
        else:
            add("record", "A typical record", row)
        if row.no_text:
            add("no_text", "No text", row)
        if row.no_time:
            add("no_time", "No time recorded", row)
        if row.deleted_state and row.deleted_state != "Intact":
            add("deleted", "Deleted on the phone", row)
    keep_apps = sorted(apps, key=lambda a: (-apps[a], a))[:MAX_APP_KINDS]
    for row in rows:
        if row.is_event and row.app in keep_apps:
            add("app:" + row.app, "In " + row.app, row)
    order = ["direction:incoming", "direction:outgoing", "direction:unknown", "one_to_one", "group", "record"]
    out = sorted(kinds.values(), key=lambda k: (order.index(k["id"]) if k["id"] in order else len(order), k["id"]))
    for i, k in enumerate(out, 1):
        k.pop("h")
        k["number"] = i
        k["example"] = _example(conn, call, k["record_uid"])
    return {"id": str(call.id), "records": len(rows), "kinds": out, "apps_not_shown": max(0, len(apps) - len(keep_apps))}


def _example(conn, call, record_uid):
    g = call.current_generation
    ev = conn.execute(text("SELECT kind, direction, app, sort_instant, body, subject, thread_key FROM phone_comm_events "
                           "WHERE record_uid = :r AND generation = :g"), {"r": record_uid, "g": g}).one_or_none()
    rs = conn.execute(text("SELECT model_type, title, first_instant, deleted_state FROM phone_record_summaries WHERE "
                           "record_uid = :r AND generation = :g"), {"r": record_uid, "g": g}).one_or_none()
    parties = [{"role": p.role if p.role_basis != "owner_implicit" else p.implied_role,
                "name": p.name_in_record, "identifier": p.identifier_raw, "is_owner": bool(p.is_phone_owner) or
                p.role_basis == "owner_implicit", "implicit_owner": p.role_basis == "owner_implicit",
                "mapped_by_this": p.mapping_row_id == call.rule_id}
               for p in conn.execute(text(
                   "SELECT role, role_basis, implied_role, name_in_record, identifier_raw, is_phone_owner, mapping_row_id "
                   "FROM phone_participations WHERE record_uid = :r AND generation = :g ORDER BY ordinal, participation_uid"),
                   {"r": record_uid, "g": g})]
    times = [{"field": apply.words(t.field_name), "instant": t.effective_instant.isoformat() if t.effective_instant else None,
              "original_text": t.original_text, "is_event_time": bool(t.is_event_time),
              "mapped_by_this": call.rule_id in (t.mapping_row_id, t.meaning_mapping_row_id)}
             for t in conn.execute(text(
                 "SELECT field_name, effective_instant, original_text, is_event_time, mapping_row_id, "
                 "meaning_mapping_row_id FROM phone_time_values WHERE record_uid = :r AND generation = :g "
                 "ORDER BY ordinal, value_index"), {"r": record_uid, "g": g})]
    return {"record_uid": record_uid, "type_words": apply.words(rs.model_type) if rs else None,
            "kind": ev.kind if ev else None, "direction": ev.direction if ev else None, "app": ev.app if ev else None,
            "instant": (ev.sort_instant if ev else (rs.first_instant if rs else None)).isoformat()
            if (ev and ev.sort_instant) or (not ev and rs and rs.first_instant) else None,
            "text": (ev.body if ev else None), "subject": ev.subject if ev else None,
            "title": rs.title if rs else None, "deleted_state": rs.deleted_state if rs else None,
            "parties": parties, "times": times}


# ---- deciding --------------------------------------------------------------------------------------------------

def _key(call):
    return "reading:%s@%s" % (call.rule_id, call.mapping_version_id)


def standard_reason(n_examples, n_kinds):
    return "Confirmed on the review screen after viewing %d examples across %d kinds" % (n_examples, n_kinds)


def _check_current(call, expected_status):
    """The person decided on what they saw: a reading that changed since is refused with 07 J-8's wording (RQ-6),
    "[name] confirmed this 2 minutes ago. Your view is updated." """
    if call.status != expected_status:
        verb = {"confirmed": "confirmed", "corrected": "corrected"}.get(call.status, "reopened")
        ago = ""
        if call.resolved_at is not None:
            mins = max(0, int((datetime.now(timezone.utc) - call.resolved_at).total_seconds() // 60))
            ago = " just now" if mins == 0 else " %d minute%s ago" % (mins, "" if mins == 1 else "s")
        raise Conflict("%s %s this%s. Your view is updated." % (call.resolved_by or "Someone", verb, ago))


def _before(after, known):
    """The ledger reads a decision as a diff, so both sides carry the same fields: what the decision adds (the
    examples seen, the scope, a note) was absent before it, recorded as None."""
    return {k: known.get(k) for k in after}


def confirm(db, case_id, judgement_id, *, viewed, actor, note=None, opened=None, expected_status="open",
            listed_with=None) -> dict:
    """Looks right. ``viewed``: the example kinds the person viewed; every kind must be in it. Only an open reading
    is confirmed; a corrected one goes back to the mapping's choice by another correction (8.8). ``listed_with``:
    the number of rows shown together when this one is confirmed by ``confirm_kind``; it is kept on the decision."""
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from postgres.models.phone_extraction import PhoneExtraction
    from services import manual_changes
    from services.financial import decisions
    conn = db.connection()
    call = _call(conn, case_id, judgement_id, lock=True)
    _check_current(call, expected_status)
    if call.status != "open":
        raise Conflict("This reading was corrected. To go back to the system's reading, correct it again.")
    shown = examples(conn, case_id, judgement_id)["kinds"]
    missing = [k["label"] for k in shown if k["id"] not in set(viewed or ())]
    if missing:
        raise ReadingError("Open every kind of example first: %s." % ", ".join(missing))
    opened_set = set(opened if opened is not None else viewed)
    examples_record = [{"kind": k["id"], "record_uid": k["record_uid"], "opened": k["id"] in opened_set} for k in shown]
    reason = standard_reason(len(shown), len(shown))
    ext = db.get(PhoneExtraction, call.extraction_id)
    after = {_key(call): "reviewed", "examples": examples_record, "rule_part": call.rule_part,
             "note": note.strip() if note and note.strip() else None}
    if listed_with is not None:
        after["listed_with_rows"] = int(listed_with)
    row = decisions.record(db, case_id=ext.case_id, subject=ext, subject_type=AdjudicationSubject.phone_extraction,
                           decision=AdjudicationDecision.confirm_phone_reading, reason=reason, actor=actor,
                           before=_before(after, {_key(call): "applied_unconfirmed", "rule_part": call.rule_part}),
                           after=after, reason_kind="standard")
    _resolve(conn, call, "confirmed", actor, reason, row.id)
    _set_level(conn, call, "reviewed")
    manual_changes.record_confirmation(db, "phone_reading", case_id, {"type": "phone_extraction", "id": str(ext.id)},
                                       {"rule": call.rule_id, "reading": "reviewed"}, actor, reason,
                                       link="/cases/%s/phone-review" % case_id,
                                       pattern_key=manual_changes.make_pattern_key("phone_reading", call.rule_id,
                                                                                   call.mapping_name, call.type_name))
    return {"decision_id": str(row.id), "status": "confirmed", "reason": reason, "reason_kind": "standard",
            "resolved_by": actor.name}


def confirm_kind(db, case_id, rows, *, actor, note=None) -> dict:
    """"Looks right for all 12 rows of this kind on this phone" (07 J-8 step 6). A kind is one rule part on one phone
    (UXD-58). ``rows`` are the rows the person was shown, each with the example kinds shown for it: only those are
    confirmed, each by ``confirm`` as a decision of its own under this person, so a row is refused exactly as it
    would be alone (changed since it was listed, a kind of example not shown). A refused row leaves the others
    standing and is stated. An open row of the kind that was not listed stays open and is counted."""
    if not rows:
        raise ReadingError("No rows were listed.")
    conn = db.connection()
    items = {i["id"]: i for i in queue(conn, case_id)["items"]}
    known = [items[str(r["id"])] for r in rows if str(r["id"]) in items]
    if not known:
        raise NotFound("None of these readings is in this case now.")
    phone, part = known[0]["extraction_id"], known[0]["part"]
    listed = {str(r["id"]) for r in rows}
    done, refused = [], []
    for r in rows:
        rid = str(r["id"])
        item = items.get(rid)
        if item is None or (item["extraction_id"], item["part"]) != (phone, part):
            refused.append({"id": rid, "sentence": item["sentence"] if item else None,
                            "reason": "This row is not of this kind on this phone now, so it was not confirmed."})
            continue
        try:
            with db.begin_nested():
                out = confirm(db, case_id, rid, viewed=r.get("viewed"), opened=r.get("opened"), note=note, actor=actor,
                              listed_with=len(rows))
            done.append({"id": rid, "sentence": item["sentence"], "decision_id": out["decision_id"],
                         "reason": out["reason"]})
        except ReadingError as exc:
            refused.append({"id": rid, "sentence": item["sentence"], "reason": str(exc)})
    not_listed = sum(1 for i in items.values() if i["extraction_id"] == phone and i["part"] == part and
                     i["status"] == "open" and i["id"] not in listed)
    words = "Confirmed %s under your name, each as its own decision." % _rows(len(done))
    if refused:
        words += " %s refused." % _rows(len(refused), was=True)
    if not_listed:
        words += " %s not listed and stayed open." % _rows(not_listed, was=True)
    return {"confirmed": done, "refused": refused, "not_listed": not_listed, "resolved_by": actor.name, "words": words}


def _rows(n, was=False):
    out = "%s row%s" % ("{:,}".format(n), "" if n == 1 else "s")
    return out + ((" was" if n == 1 else " were") if was else "")


def same_format_phones(conn, call):
    """The case's other active phones with the same report format (producer and report version), by label."""
    return [str(r[0]) for r in conn.execute(text(
        "SELECT o.id FROM phone_extractions e JOIN phone_extractions o ON o.case_id = e.case_id AND o.id <> e.id AND "
        "o.standing = 'active' AND o.report_version IS NOT DISTINCT FROM e.report_version AND o.producer_version IS "
        "NOT DISTINCT FROM e.producer_version WHERE e.id = :e ORDER BY o.created_at, o.id"), {"e": call.extraction_id})]


def _scope_targets(conn, call, scope):
    targets = [str(call.extraction_id)]
    if scope == "same_format":
        targets += same_format_phones(conn, call)
    elif scope != "this_phone":
        raise ReadingError("The scope is this phone or the phones with the same report format.")
    return targets


def _empty_count(conn, call, chosen, extraction_id):
    """(records of this phone that would lose the value, what they would be without), read from the rows the rule
    wrote at the phone's current generation. Nothing is written."""
    params = {"e": extraction_id, "r": call.rule_id, "mv": call.mapping_version_id}
    generation = "(SELECT generation FROM phone_interpretation_state WHERE extraction_id = :e)"
    root = "coalesce(root_record_uid, record_uid)"
    if call.rule_part == "role":
        old = _evidence(conn, call).get("choice")
        if not old or old == chosen["choice"]:
            return 0, None
        params["old"] = old
        n = conn.execute(text(
            "WITH mine AS (SELECT DISTINCT " + root + " AS r FROM phone_participations WHERE extraction_id = :e AND "
            "generation = " + generation + " AND mapping_row_id = :r AND mapping_version_id = :mv AND role = :old), "
            "others AS (SELECT DISTINCT " + root + " AS r FROM phone_participations WHERE extraction_id = :e AND "
            "generation = " + generation + " AND mapping_row_id IS DISTINCT FROM :r AND "
            "(role = :old OR implied_role = :old)) "
            "SELECT count(*) FROM mine LEFT JOIN others USING (r) WHERE others.r IS NULL"), params).scalar()
        return int(n), "no %s" % apply.words(old)
    if call.rule_part == "event_time":
        params["f"] = chosen["choice"]
        n = conn.execute(text(
            "WITH mine AS (SELECT DISTINCT " + root + " AS r FROM phone_time_values WHERE extraction_id = :e AND "
            "generation = " + generation + " AND mapping_row_id = :r AND mapping_version_id = :mv AND "
            "effective_instant IS NOT NULL), "
            "kept AS (SELECT DISTINCT " + root + " AS r FROM phone_time_values WHERE extraction_id = :e AND "
            "generation = " + generation + " AND field_name = :f AND effective_instant IS NOT NULL) "
            "SELECT count(*) FROM mine LEFT JOIN kept USING (r) WHERE kept.r IS NULL"), params).scalar()
        return int(n), "no time"
    return 0, None  # a time's meaning changes its words, never whether it is there


def correction_preview(conn, case_id, judgement_id, *, choice_id, scope="this_phone") -> dict:
    """What a correction would leave empty, before anything is written (07 J-8): the true count per phone in scope,
    and the sentence "After this change, 2,140 messages will have no sender."."""
    call = _call(conn, case_id, judgement_id)
    options = {c["id"]: c for c in choices(conn, call)}
    if choice_id not in options:
        raise ReadingError("Choose one of the offered corrections.")
    labels = phone_labels(conn, case_id)
    noun, one = plural(apply.words(call.type_name)), apply.words(call.type_name)
    phones, total, without = [], 0, None
    for ext_id in _scope_targets(conn, call, scope):
        n, what = _empty_count(conn, call, options[choice_id], ext_id)
        phones.append({"extraction_id": ext_id, "phone": labels.get(ext_id, ext_id), "records": n})
        total += n
        without = what or without
    words = None
    if total:
        words = "After this change, %s %s will have %s." % ("{:,}".format(total), noun if total != 1 else one, without)
    return {"records": total, "without": without, "phones": phones, "words": words}


def correct(db, case_id, judgement_id, *, choice_id, reason, actor, scope="this_phone", note=None,
            expected_status="open", expected_empty=None) -> dict:
    """Not right: a choice from the closed list and a typed reason. Re-derives only the phones in scope. Allowed on
    a confirmed reading too: a correction is the confirmation's reversal (8.8). ``expected_empty``: the count of
    ``correction_preview`` the person agreed to (the route always passes it, 0 when none was shown); if the true
    count now differs, nothing is written and the new sentence is the answer."""
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from postgres.models.phone_extraction import PhoneExtraction
    from services import manual_changes
    from services.financial import decisions
    if not reason or not reason.strip():
        raise ReadingError("A correction needs a reason in your own words.")
    conn = db.connection()
    call = _call(conn, case_id, judgement_id, lock=True)
    _check_current(call, expected_status)
    options = {c["id"]: c for c in choices(conn, call)}
    if choice_id not in options:
        raise ReadingError("Choose one of the offered corrections.")
    chosen = options[choice_id]
    targets = _scope_targets(conn, call, scope)
    if expected_empty is not None:
        preview = correction_preview(conn, case_id, judgement_id, choice_id=choice_id, scope=scope)
        if preview["records"] != int(expected_empty):
            raise Conflict((preview["words"] or "This correction would now leave nothing empty.") +
                           " Continue or cancel.")
    labels = phone_labels(conn, case_id)
    original = _evidence(conn, call).get("choice") if call.rule_part != "meaning" else \
        (_evidence(conn, call).get("row") or {}).get("outputs")
    first = None
    for ext_id in targets:
        ext = db.get(PhoneExtraction, uuid.UUID(ext_id))
        after = {_key(call): chosen["choice"], "scope": targets, "choice_label": chosen["label"],
                 "rule_part": call.rule_part, "note": note.strip() if note and note.strip() else None}
        row = decisions.record(db, case_id=ext.case_id, subject=ext, subject_type=AdjudicationSubject.phone_extraction,
                               decision=AdjudicationDecision.correct_phone_reading, reason=reason.strip(), actor=actor,
                               before=_before(after, {_key(call): original, "rule_part": call.rule_part}), after=after)
        first = first or row
    _resolve(conn, call, "corrected", actor, reason.strip(), first.id)
    conn.execute(text(
        "INSERT INTO phone_mapping_proposals (id, kind, name, content, origin, decision_id, state, case_id) VALUES "
        "(:id, :k, :n, CAST(:c AS jsonb), 'case_correction', :d, 'draft', :case)"),
        {"id": uuid.uuid4(), "k": call.mapping_kind, "n": call.mapping_name, "d": first.id, "case": case_id,
         "c": __import__("json").dumps({"rule_id": call.rule_id, "mapping_version_id": str(call.mapping_version_id),
                                        "from": original, "to": chosen["choice"], "label": chosen["label"]},
                                       default=str)})
    manual_changes.record_change(db, "phone_reading", case_id, {"type": "phone_extraction", "id": str(call.extraction_id)},
                                 {"rule": call.rule_id, "reading": original}, {"rule": call.rule_id,
                                                                               "reading": chosen["choice"]},
                                 actor, reason.strip(), link="/cases/%s/phone-review" % case_id,
                                 pattern_key=manual_changes.make_pattern_key("phone_reading", call.rule_id,
                                                                             call.mapping_name, call.type_name))
    return {"decision_id": str(first.id), "status": "corrected", "scope": [labels.get(t, t) for t in targets],
            "extraction_ids": targets, "choice": chosen["label"]}


def _resolve(conn, call, status, actor, reason, decision_id):
    conn.execute(text(
        "UPDATE phone_mapping_judgements SET status = :s, resolved_by = :n, resolved_by_email = :m, resolved_at = now(), "
        "resolution_reason = :r, adjudication_id = :d, updated_at = now() WHERE id = :j"),
        {"s": status, "n": actor.name, "m": actor.email, "r": reason, "d": decision_id, "j": call.id})


LEVEL_TABLES = ("phone_time_values", "phone_location_points", "phone_unplaced_records", "phone_participations",
                "phone_texts", "phone_address_texts", "phone_record_summaries", "phone_comm_events", "phone_threads")


def _set_level(conn, call, level):
    """Rows the rule produced on the current generation take the confirmed level now; the re-derive that the new
    decision triggers writes the same."""
    p = {"e": call.extraction_id, "g": call.current_generation, "r": call.rule_id, "mv": call.mapping_version_id,
         "lvl": level}
    if call.rule_part == "meaning":
        conn.execute(text("UPDATE phone_time_values SET meaning_level = :lvl WHERE extraction_id = :e AND generation = :g "
                          "AND meaning_mapping_row_id = :r AND meaning_mapping_version_id = :mv"), p)
        return
    for t in LEVEL_TABLES:
        conn.execute(text("UPDATE %s SET interpretation_level = :lvl WHERE extraction_id = :e AND generation = :g AND "
                          "mapping_row_id = :r AND mapping_version_id = :mv" % t), p)


# ---- hooks for the applier and the sweep -------------------------------------------------------------------------

def reading_decisions(conn, extraction_id) -> dict:
    """``{(rule_id, mapping_version_id): {...}}`` from this phone's current reading decisions (latest wins)."""
    out = {}
    for r in conn.execute(text(
            "SELECT id, decision, after, actor_name, actor_email, created_at, reason FROM adjudications WHERE "
            "subject_type = 'phone_extraction' AND subject_id = :e AND decision = ANY(CAST(:d AS text[])) "
            "ORDER BY subject_sequence"), {"e": extraction_id, "d": list(READING_DECISIONS)}):
        for k, v in (r.after or {}).items():
            if not k.startswith("reading:"):
                continue
            rule, _, mv = k[len("reading:"):].rpartition("@")
            out[(rule, mv)] = {"decision": "confirm" if r.decision == "confirm_phone_reading" else "correct",
                               "choice": v, "decision_id": r.id, "by": r.actor_name, "by_email": r.actor_email,
                               "at": r.created_at, "reason": r.reason}
    return out


def decision_revision(conn, extraction_id):
    from services.phone import corrections
    ids = [str(r[0]) for r in conn.execute(text(
        "SELECT id FROM adjudications WHERE subject_type = 'phone_extraction' AND subject_id = :e AND "
        "decision = ANY(CAST(:d AS text[])) ORDER BY subject_sequence"),
        {"e": extraction_id, "d": list(DERIVING_DECISIONS)})]
    ids += corrections.record_decision_ids(conn, extraction_id)  # a value correction re-derives its phone (10.3)
    return hashlib.sha256("|".join(ids).encode()).hexdigest()[:32] if ids else None


def latest_extraction_decision(conn, extraction_id, decision):
    return conn.execute(text(
        "SELECT id, after, actor_name, created_at FROM adjudications WHERE subject_type = 'phone_extraction' AND "
        "subject_id = :e AND decision = :d ORDER BY subject_sequence DESC LIMIT 1"),
        {"e": extraction_id, "d": decision}).one_or_none()


def region_decision(conn, extraction_id):
    r = latest_extraction_decision(conn, extraction_id, "set_phone_default_region")
    return (r.after or {}).get("default_region") if r else None


def owner_decision(conn, extraction_id):
    r = latest_extraction_decision(conn, extraction_id, "set_phone_owner")
    if r is None or not (r.after or {}).get("owner_identity_keys"):
        return None
    return {"identity_keys": list(r.after["owner_identity_keys"]), "decision_id": str(r.id), "by": r.actor_name,
            "at": r.created_at.isoformat()}


def progress(conn, case_id) -> list:
    """Re-reading progress of the case's phones (07 J-8 step 4): true counts from the running pass."""
    labels = phone_labels(conn, case_id)
    out = []
    for r in conn.execute(text(
            "SELECT e.id, s.status, p.records_total, p.records_done, p.started_at, p.updated_at, p.finished_at, "
            "s.decision_revision FROM phone_extractions e LEFT JOIN phone_interpretation_state s ON s.extraction_id = e.id "
            "LEFT JOIN phone_interpretation_progress p ON p.extraction_id = e.id WHERE e.case_id = :c AND "
            "e.standing = 'active' ORDER BY e.created_at, e.id"), {"c": case_id}):
        running = r.finished_at is None and r.started_at is not None
        pending = not running and (r.decision_revision or None) != (decision_revision(conn, r.id) or None)
        left = None
        if running and r.records_done and r.records_total and r.updated_at and r.started_at:
            rate = r.records_done / max(1.0, (r.updated_at - r.started_at).total_seconds())
            left = int(max(0, r.records_total - r.records_done) / rate) if rate > 0 else None
        out.append({"extraction_id": str(r.id), "phone": labels.get(str(r.id)), "state": "waiting" if pending else
                    ("re-reading" if running else "done"), "records_total": int(r.records_total or 0),
                    "records_done": int(r.records_done or 0), "seconds_left": left})
    return out


def install():
    from services.phone import identities, sweep
    apply.register_reading_decisions(reading_decisions)
    apply.register_region_decision(region_decision)
    identities.register_owner_decision(owner_decision)
    sweep.register_decision_revision(decision_revision)
