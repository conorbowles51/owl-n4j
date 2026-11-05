"""Link state (docs/cellebrite/07 section 6.3; CO-8, CO-15).

A link's state is worked out when the link is shown, and the stored link is never rewritten. The states beside
"from a replaced copy" (``replaced_links``):

- **corrected since collected**: a person corrected a value of the record after the link was made. Both values are
  shown, the value as collected and the value in effect; only the value in effect is read anywhere else.
- **reading changed since collected**: a new reading of the phone (a corrected reading, a clock offset, a new mapping)
  changed who sent it, who received it, its direction or its time. Earlier readings are purged after each swap, so
  ``note_reading_changes`` records the change while both exist, for records some link collects. The person who added
  the link is offered Keep or Remove and told through the attention feed: one item with the true count.
- **set aside as a duplicate**: a linked record is one of several copies of an event and the lists show another copy.

A record corrected by a person shows as corrected, not as a changed reading: a correction of a time or a text is left
out of the comparison in the pass that applies it.

What is compared is the stored ``mapping_versions`` of the link (the generation it was collected on) against the
changes written since. A link with no generation for that phone falls back to the time it was made. A link collected
before changes were recorded says the phone was read again and that what changed was not kept.
"""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from services.phone import replaced_links
from services.phone.labels import RECIPIENT_ROLES, SENDER_ROLES
from services.phone.sensitive import MASK

# the most values one link lists on screen; the counts are always the true totals and a clipped list says so
LIST_MAX = 50
COLLECTING_TYPES = ("phone_record", "phone_selection", "phone_thread")
FIELD_WORDS = {"sender": "Sender", "recipients": "Recipients", "direction": "Direction", "time": "Time"}
SET_ASIDE = "Set aside as a duplicate: this is a copy of an event the lists show once, as another record."
OWNER_WORDS = "the phone's owner"
NOT_RECORDED = "not recorded"
# Decisions that re-read a phone and can change a reading; a value correction is the corrected state instead.
CAUSES = ("correct_phone_reading", "set_phone_clock_offset", "set_phone_device_zone", "set_phone_default_region",
          "apply_phone_zone_to_offsetless")


class LinkStateError(ValueError):
    status = 422


class NotYours(LinkStateError):
    status = 403


class Changed(LinkStateError):
    status = 409


class Missing(LinkStateError):
    status = 404


@dataclass
class Link:
    kind: str  # entry, dossier or assessment
    id: str
    container_id: str
    target_type: str
    target_id: str
    anchor: dict
    created_at: datetime | None
    adder_id: str | None
    adder: str | None
    label: str | None = None
    records: list = field(default_factory=list)


def _day(at) -> str:
    return at.astimezone(timezone.utc).strftime("%-d %B %Y") if at else "an unknown date"


def _time(at) -> str | None:
    return at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if at else None


# ---- recording what a new reading changed ----------------------------------------------------------------------

def _linked_records(conn, case_id, extraction_id, generation) -> list:
    """The records of this phone some finding, note, theory, dossier or assessment collects, directly, inside a
    selection or inside a conversation."""
    ids, threads = set(), set()
    for kind, target in conn.execute(text(
            "SELECT target_type, target_id FROM workspace_entry_links WHERE case_id = :c AND target_type = ANY(:t) "
            "UNION SELECT target_type, target_id FROM dossier_links WHERE case_id = :c AND target_type = ANY(:t) "
            "UNION SELECT target_type, target_id FROM dossier_assessment_links WHERE case_id = :c AND "
            "target_type = ANY(:t)"), {"c": case_id, "t": list(COLLECTING_TYPES)}):
        if kind == "phone_record":
            ids.add(str(target).lower())
        elif kind == "phone_thread":
            threads.add(target)
    ids.update(str(r).lower() for r in conn.execute(text(
        "SELECT DISTINCT record_id FROM collection_memberships WHERE case_id = :c"), {"c": case_id}).scalars())
    if threads:
        ids.update(str(r) for r in conn.execute(text(
            "SELECT DISTINCT record_uid FROM phone_comm_events WHERE extraction_id = :e AND generation = :g AND "
            "thread_key = ANY(:t)"), {"e": extraction_id, "g": generation, "t": sorted(threads)}).scalars())
    if not ids:
        return []
    return [str(r) for r in conn.execute(text(
        "SELECT record_uid FROM phone_record_summaries WHERE extraction_id = :e AND generation = :g AND "
        "record_uid::text = ANY(:u)"), {"e": extraction_id, "g": generation, "u": sorted(ids)}).scalars()]


def _person(row) -> str:
    who = row.name_in_record or None
    ident = row.identifier_raw or None
    if row.role == "owner_implicit" and not who and not ident:
        return OWNER_WORDS
    if who and ident:
        return "%s (%s)" % (who, ident)
    return who or ident or OWNER_WORDS if row.is_phone_owner else (who or ident or NOT_RECORDED)


def _reading(conn, extraction_id, generation, uids) -> dict:
    """``{record_uid: {field: text}}``: who, direction and time as this generation reads them."""
    out = defaultdict(dict)
    for r in conn.execute(text(
            "SELECT record_uid::text AS uid, first_instant FROM phone_record_summaries WHERE extraction_id = :e AND "
            "generation = :g AND record_uid::text = ANY(:u)"), {"e": extraction_id, "g": generation, "u": uids}):
        out[r.uid]["time"] = _time(r.first_instant)
    for r in conn.execute(text(
            "SELECT DISTINCT ON (record_uid) record_uid::text AS uid, direction, sort_instant FROM phone_comm_events "
            "WHERE extraction_id = :e AND generation = :g AND record_uid::text = ANY(:u) ORDER BY record_uid, "
            "event_uid"), {"e": extraction_id, "g": generation, "u": uids}):
        out[r.uid].update(direction=r.direction, time=_time(r.sort_instant))
    people = defaultdict(lambda: defaultdict(set))
    for r in conn.execute(text(
            "SELECT record_uid::text AS uid, role, implied_role, is_phone_owner, name_in_record, identifier_raw FROM "
            "phone_participations WHERE extraction_id = :e AND generation = :g AND record_uid::text = ANY(:u)"),
            {"e": extraction_id, "g": generation, "u": uids}):
        role = r.implied_role or r.role
        side = "sender" if role in SENDER_ROLES else ("recipients" if role in RECIPIENT_ROLES else None)
        if side:
            people[r.uid][side].add(_person(r))
    for uid, sides in people.items():
        for side, names in sides.items():
            out[uid][side] = ", ".join(sorted(names))
    return out


def _corrected_fields(conn, extraction_id, since) -> dict:
    """``{record_uid: {value types}}`` of value corrections made since the last reading: their change is shown as
    corrected, with both values, not as a changed reading."""
    out = defaultdict(set)
    for uid, kind in conn.execute(text(
            "SELECT record_uid::text, value_type FROM phone_value_corrections WHERE extraction_id = :e AND "
            "(CAST(:s AS timestamptz) IS NULL OR created_at > :s)"), {"e": extraction_id, "s": since}):
        out[uid].add(kind)
    return out


def _cause(conn, extraction_id, since):
    """The latest decision on this phone since the last reading, or None for a re-reading no person asked for (a new
    mapping or interpreter)."""
    return conn.execute(text(
        "SELECT id, actor_name, created_at FROM adjudications WHERE subject_type = 'phone_extraction' AND subject_id = "
        ":e AND decision = ANY(CAST(:d AS text[])) AND (CAST(:s AS timestamptz) IS NULL OR created_at > :s) ORDER BY "
        "subject_sequence DESC LIMIT 1"), {"e": extraction_id, "d": list(CAUSES), "s": since}).first()


def note_reading_changes(conn, case_id, extraction_id, old_generation, new_generation) -> int:
    """Called in the swap's transaction, while both generations exist: one row per changed field of a collected
    record. Bounded by what is collected, not by what the re-reading touched. Returns the rows written."""
    uids = _linked_records(conn, case_id, extraction_id, old_generation)
    if not uids:
        return 0
    before = _reading(conn, extraction_id, old_generation, uids)
    after = _reading(conn, extraction_id, new_generation, uids)
    since = conn.execute(text("SELECT interpreted_at FROM phone_interpretation_state WHERE extraction_id = :e"),
                         {"e": extraction_id}).scalar()
    corrected = _corrected_fields(conn, extraction_id, since)
    rows = []
    for uid in uids:
        kinds = corrected.get(uid, ())
        skip = ({"time"} if "TimeStamp" in kinds else set()) | ({"sender", "recipients"} if "String" in kinds else set())
        for name in FIELD_WORDS:
            was, now = before.get(uid, {}).get(name), after.get(uid, {}).get(name)
            if name not in skip and was != now:
                rows.append({"c": case_id, "e": extraction_id, "r": uid, "f": name, "w": was, "n": now,
                             "og": old_generation, "ng": new_generation})
    if rows:
        why = _cause(conn, extraction_id, since)
        for row in rows:
            row.update(d=why.id if why else None, b=why.actor_name if why else None,
                       a=why.created_at if why else datetime.now(timezone.utc))
        conn.execute(text(
            "INSERT INTO phone_reading_changes (case_id, extraction_id, record_uid, field, was_text, now_text, "
            "from_generation, to_generation, decision_id, decided_by, changed_at) VALUES (:c, :e, CAST(:r AS uuid), "
            ":f, :w, :n, :og, :ng, :d, :b, :a)"), rows)
    return len(rows)


# ---- the links of a finding or a dossier ---------------------------------------------------------------------------

def _anchor(value) -> dict:
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


def entry_links(conn, case_id, entry_id) -> list:
    return [Link("entry", str(r.id), str(entry_id), r.target_type, r.target_id, _anchor(r.source_anchor), r.created_at,
                 str(r.created_by_user_id) if r.created_by_user_id else None, r.name, r.target_label)
            for r in conn.execute(text(
                "SELECT l.*, u.name FROM workspace_entry_links l LEFT JOIN users u ON u.id = l.created_by_user_id "
                "WHERE l.case_id = :c AND l.entry_id = :i AND l.target_type = ANY(:t) ORDER BY l.created_at, l.id"),
                {"c": case_id, "i": entry_id, "t": list(COLLECTING_TYPES)})]


def dossier_links(conn, case_id, dossier_id) -> list:
    out = [Link("dossier", str(r.id), str(dossier_id), r.target_type, r.target_id, _anchor(r.source_anchor),
                r.created_at, str(r.created_by_user_id) if r.created_by_user_id else None, r.name, r.label)
           for r in conn.execute(text(
               "SELECT l.*, u.name FROM dossier_links l LEFT JOIN users u ON u.id = l.created_by_user_id WHERE "
               "l.case_id = :c AND l.dossier_id = :i AND l.target_type = ANY(:t) ORDER BY l.created_at, l.id"),
               {"c": case_id, "i": dossier_id, "t": list(COLLECTING_TYPES)})]
    out += [Link("assessment", str(r.id), str(dossier_id), r.target_type, r.target_id, _anchor(r.source_anchor),
                 r.created_at, str(r.author_user_id) if r.author_user_id else None, r.name, r.label)
            for r in conn.execute(text(
                "SELECT l.*, a.author_user_id, u.name FROM dossier_assessment_links l JOIN dossier_assessments a ON "
                "a.id = l.assessment_id LEFT JOIN users u ON u.id = a.author_user_id WHERE l.case_id = :c AND "
                "a.dossier_id = :i AND l.target_type = ANY(:t) ORDER BY l.created_at, l.id"),
                {"c": case_id, "i": dossier_id, "t": list(COLLECTING_TYPES)})]
    return out


def links_added_by(conn, case_id, user_id) -> list:
    """Every collecting link this person added in the case, on entries and dossiers that are still in use."""
    out = [Link("entry", str(r.id), str(r.entry_id), r.target_type, r.target_id, _anchor(r.source_anchor), r.created_at,
                str(user_id), None, r.target_label)
           for r in conn.execute(text(
               "SELECT l.* FROM workspace_entry_links l JOIN workspace_entries e ON e.id = l.entry_id WHERE l.case_id "
               "= :c AND l.created_by_user_id = :u AND l.target_type = ANY(:t) AND e.deleted_at IS NULL"),
               {"c": case_id, "u": user_id, "t": list(COLLECTING_TYPES)})]
    out += [Link("dossier", str(r.id), str(r.dossier_id), r.target_type, r.target_id, _anchor(r.source_anchor),
                 r.created_at, str(user_id), None, r.label)
            for r in conn.execute(text(
                "SELECT l.* FROM dossier_links l JOIN case_profiles p ON p.id = l.dossier_id WHERE l.case_id = :c AND "
                "l.created_by_user_id = :u AND l.target_type = ANY(:t) AND p.archived_at IS NULL"),
                {"c": case_id, "u": user_id, "t": list(COLLECTING_TYPES)})]
    out += [Link("assessment", str(r.id), str(r.dossier_id), r.target_type, r.target_id, _anchor(r.source_anchor),
                 r.created_at, str(user_id), None, r.label)
            for r in conn.execute(text(
                "SELECT l.*, a.dossier_id FROM dossier_assessment_links l JOIN dossier_assessments a ON a.id = "
                "l.assessment_id WHERE l.case_id = :c AND a.author_user_id = :u AND l.target_type = ANY(:t)"),
                {"c": case_id, "u": user_id, "t": list(COLLECTING_TYPES)})]
    return out


def _expand(conn, case_id, links) -> None:
    """Fill each link's records, in one query per kind of link, never one per link."""
    selections = {str(l.target_id) for l in links if l.target_type == "phone_selection"}
    threads = {l.target_id for l in links if l.target_type == "phone_thread"}
    members, in_thread = {}, defaultdict(list)
    if selections:
        for sid, uids in conn.execute(text(
                "SELECT id::text, record_uids FROM phone_selections WHERE case_id = :c AND id::text = ANY(:s)"),
                {"c": case_id, "s": sorted(selections)}):
            members[sid] = [str(u).lower() for u in uids or []]
    if threads:
        for key, uid in conn.execute(text(
                "SELECT ev.thread_key, ev.record_uid::text FROM phone_comm_events ev JOIN phone_interpretation_state st "
                "ON st.extraction_id = ev.extraction_id AND st.generation = ev.generation WHERE ev.case_id = :c AND "
                "ev.thread_key = ANY(:t)"), {"c": case_id, "t": sorted(threads)}):
            in_thread[key].append(uid)
    for link in links:
        if link.target_type == "phone_record":
            link.records = [str(link.target_id).lower()]
        elif link.target_type == "phone_selection":
            link.records = members.get(str(link.target_id), [])
        else:
            link.records = in_thread.get(link.target_id, [])


def _collected_generations(link) -> Any:
    """``{extraction_id: generation}`` for a selection's stored version set, or the one generation of a record or
    conversation link, or None when the link holds none."""
    versions = link.anchor.get("mapping_versions") or {}
    if isinstance(versions.get("phones"), list):
        return {str(p.get("extraction_id")): p.get("generation") for p in versions["phones"]
                if isinstance(p, dict) and p.get("extraction_id")} or None
    return versions.get("generation")


def _after_collection(link, row) -> bool:
    held = _collected_generations(link)
    generation = held.get(str(row.extraction_id)) if isinstance(held, dict) else held
    if isinstance(generation, int):
        return row.to_generation > generation
    return bool(link.created_at and row.changed_at > link.created_at)


def _reading_items(link, rows) -> dict:
    """``{(record, field): item}``: from the reading at collection to the reading now. A change undone by a later one
    leaves nothing."""
    grouped = defaultdict(list)
    for row in rows:
        if _after_collection(link, row):
            grouped[(str(row.record_uid), row.field)].append(row)
    out = {}
    for key, seq in grouped.items():
        first, last = seq[0], seq[-1]
        if first.was_text == last.now_text:
            continue
        by = last.decided_by
        tail = ("by %s on %s" % (by, _day(last.changed_at))) if by else (
            "when the phone was read again on %s" % _day(last.changed_at))
        out[key] = {"record_uid": key[0], "field": key[1], "was": first.was_text, "now": last.now_text, "by": by,
                    "at": last.changed_at.isoformat(), "seq": last.seq,
                    "words": "%s was %s, now %s, %s." % (FIELD_WORDS[key[1]], first.was_text or NOT_RECORDED,
                                                         last.now_text or NOT_RECORDED, tail)}
    return out


def _corrected_items(link, rows, masked) -> list:
    """Each value whose text in effect differs from its text when the link was made. Both are shown."""
    chains = defaultdict(list)
    for row in rows:
        chains[(str(row.record_uid), row.field_path, row.value_index)].append(row)
    out = []
    for (uid, path, index), chain in chains.items():
        held = chain[0].machine_text
        for row in chain:
            if link.created_at is None or row.created_at <= link.created_at:
                held = row.corrected_text
        last = chain[-1]
        if held == last.corrected_text:
            continue
        hidden = (uid, path, index) in masked
        was, now = (MASK, MASK) if hidden else (held, last.corrected_text)
        from services.phone.mappings import apply
        name = apply.words(path.split(".")[-1].split("[")[0])
        out.append({"record_uid": uid, "field": path, "field_words": name, "was": was, "now": now, "by": last.actor_name,
                    "at": last.created_at.isoformat(), "reason": last.reason, "masked": hidden,
                    "words": "%s: as collected %s, now %s, corrected by %s on %s." % (
                        name[:1].upper() + name[1:], was or NOT_RECORDED, now, last.actor_name, _day(last.created_at))})
    return out


def _bulk(conn, case_id, links) -> dict:
    uids = sorted({u for l in links for u in l.records})
    empty = {"changes": defaultdict(list), "corrections": defaultdict(list), "masked": set(), "choices": defaultdict(list),
             "aside": {}, "phones": {}, "state": {}}
    if not uids:
        return empty
    out = empty
    for r in conn.execute(text(
            "SELECT seq, extraction_id, record_uid, field, was_text, now_text, to_generation, decided_by, changed_at "
            "FROM phone_reading_changes WHERE case_id = :c AND record_uid::text = ANY(:u) ORDER BY seq"),
            {"c": case_id, "u": uids}):
        out["changes"][str(r.record_uid)].append(r)
    for r in conn.execute(text(
            "SELECT c.record_uid, c.field_path, c.value_index, c.machine_text, c.corrected_text, c.created_at, "
            "a.actor_name, a.reason FROM phone_value_corrections c JOIN adjudications a ON a.id = c.decision_id WHERE "
            "c.case_id = :c AND c.record_uid::text = ANY(:u) ORDER BY c.created_at, c.id"), {"c": case_id, "u": uids}):
        out["corrections"][str(r.record_uid)].append(r)
    if out["corrections"]:
        out["masked"] = {(str(r[0]), r[1], r[2]) for r in conn.execute(text(
            "SELECT x.record_uid, x.field_path, x.value_index FROM phone_texts x JOIN phone_interpretation_state s ON "
            "s.extraction_id = x.extraction_id AND s.generation = x.generation WHERE x.case_id = :c AND x.is_sensitive "
            "AND x.record_uid::text = ANY(:u)"), {"c": case_id, "u": sorted(out["corrections"])})}
    for r in conn.execute(text(
            "SELECT link_id::text AS link, choice, through_seq, chosen_by, chosen_at FROM phone_link_choices WHERE "
            "link_id::text = ANY(:l) ORDER BY chosen_at"), {"l": [l.id for l in links]}):
        out["choices"][r.link].append(r)
    records = sorted({str(l.target_id).lower() for l in links if l.target_type == "phone_record"})
    if records:
        out["aside"] = _set_aside(conn, case_id, records)
    for r in conn.execute(text(
            "SELECT s.record_uid::text AS uid, st.extraction_id::text AS ext, st.generation, st.reading_changes_since, "
            "st.interpreted_at FROM phone_record_summaries s JOIN phone_interpretation_state st ON st.extraction_id = "
            "s.extraction_id AND st.generation = s.generation WHERE s.case_id = :c AND s.record_uid::text = ANY(:u)"),
            {"c": case_id, "u": uids}):
        out["phones"][r.uid] = r.ext
        out["state"][r.ext] = r
    return out


def _set_aside(conn, case_id, records) -> dict:
    """``{record_uid: record the lists show}`` for linked records that are a copy the lists do not show. The order is
    ``streams``': the copy with the most fields filled, then the lowest record id."""
    rows = conn.execute(text(
        "WITH mine AS (SELECT DISTINCT extraction_id, dup_group_uid FROM pv_comm_event WHERE case_id = :c AND dup_group_uid IS "
        "NOT NULL AND record_uid::text = ANY(:r)), ranked AS (SELECT ev.record_uid::text AS uid, ev.extraction_id, "
        "ev.dup_group_uid, row_number() OVER (PARTITION BY ev.extraction_id, ev.dup_group_uid ORDER BY "
        "(ev.body IS NOT NULL)::int + (ev.subject IS NOT NULL)::int + (ev.app IS NOT NULL)::int + "
        "(ev.sort_instant IS NOT NULL)::int + (ev.thread_key IS NOT NULL)::int + (ev.call_duration_s IS NOT NULL)::int "
        "+ (ev.status IS NOT NULL)::int DESC, ev.record_uid) AS n FROM pv_comm_event ev JOIN mine m ON m.extraction_id "
        "= ev.extraction_id AND m.dup_group_uid = ev.dup_group_uid WHERE ev.case_id = :c) SELECT a.uid, b.uid AS shown "
        "FROM ranked a JOIN ranked b ON b.extraction_id = a.extraction_id AND b.dup_group_uid = a.dup_group_uid AND "
        "b.n = 1 WHERE a.n > 1 AND a.uid = ANY(:r)"), {"c": case_id, "r": records}).fetchall()
    return {r.uid: r.shown for r in rows}


def _state_of(link, bulk, viewer_id) -> dict:
    changes = [r for u in link.records for r in bulk["changes"].get(u, ())]
    items = sorted(_reading_items(link, changes).values(), key=lambda i: (i["record_uid"], i["field"]))
    corrected = [c for u in link.records for c in _corrected_items(link, bulk["corrections"].get(u, ()), bulk["masked"])]
    aside = None
    if link.target_type == "phone_record":
        shown = bulk["aside"].get(str(link.target_id).lower())
        if shown:
            aside = {"shown_record_uid": shown, "words": SET_ASIDE}
    last_keep = next((c for c in reversed(bulk["choices"].get(link.id, ())) if c.choice == "keep"), None)
    through = max((i["seq"] for i in items), default=0)
    needs_choice = bool(items) and (last_keep is None or through > last_keep.through_seq)
    reread = None
    held = _collected_generations(link)
    for uid in link.records:
        ext = bulk["phones"].get(uid)
        st = bulk["state"].get(ext)
        generation = (held.get(ext) if isinstance(held, dict) else held) if held is not None else None
        if st is not None and isinstance(generation, int) and generation < st.reading_changes_since:
            reread = {"at": st.interpreted_at.isoformat() if st.interpreted_at else None,
                      "words": "This phone was read again after this was collected, on %s; what the reading was when "
                               "it was collected is not kept, so no change can be shown." % _day(st.interpreted_at)}
            break
    names = []
    if corrected:
        names.append("corrected")
    if items:
        names.append("reading_changed")
    if aside:
        names.append("set_aside")
    return {"link_id": link.id, "link_kind": link.kind, "target_type": link.target_type, "target_id": link.target_id,
            "states": names, "records": len(link.records),
            "corrected": {"count": len(corrected), "records": len({c["record_uid"] for c in corrected}),
                          "items": corrected[:LIST_MAX], "clipped": len(corrected) > LIST_MAX},
            "reading_changed": {"count": len(items), "records": len({i["record_uid"] for i in items}),
                                "items": items[:LIST_MAX], "clipped": len(items) > LIST_MAX},
            "set_aside": aside, "reread": reread, "added_by": link.adder, "through_seq": through,
            "needs_choice": needs_choice,
            "can_choose": needs_choice and (link.adder_id is None or str(link.adder_id) == str(viewer_id)),
            "can_remove": link.kind != "assessment",
            "kept": {"by": last_keep.chosen_by, "at": last_keep.chosen_at.isoformat(),
                     "words": "Kept by %s on %s." % (last_keep.chosen_by, _day(last_keep.chosen_at))}
            if last_keep and items else None}


def states(conn, case_id, links, viewer_id=None) -> dict:
    """``{link_id: state}`` for these links, worked out now, in one set of bulk queries whatever their number. Reads
    only; nothing about a link is stored or changed."""
    if not links:
        return {}
    _expand(conn, case_id, links)
    bulk = _bulk(conn, case_id, links)
    return {link.id: _state_of(link, bulk, viewer_id) for link in links}


def of_container(conn, case_id, container, container_id, viewer_id) -> dict:
    """The state of every phone link of one finding, note or theory (``entry``) or one dossier (``dossier``, with its
    assessments' supporting links), with the replaced-copy state of each linked record."""
    if container == "entry":
        links = entry_links(conn, case_id, container_id)
    elif container == "dossier":
        links = dossier_links(conn, case_id, container_id)
    else:
        raise LinkStateError("Link states are read for a finding or a dossier.")
    out = states(conn, case_id, links, viewer_id)
    uids = sorted({str(l.target_id).lower() for l in links if l.target_type == "phone_record"})
    replaced = {}
    for i in range(0, len(uids), replaced_links.MAX_RECORDS):
        replaced.update(replaced_links.replacements(conn, case_id, uids[i:i + replaced_links.MAX_RECORDS]))
    for link in links:
        out[link.id]["replaced"] = replaced.get(str(link.target_id).lower())
    return out


# ---- the person who added a link -----------------------------------------------------------------------------------

def outstanding(conn, case_id, user_id) -> dict | None:
    """What waits for this person's Keep or Remove in the case: one summary with true counts, however many links a
    bulk change touched. None when nothing does. A case with no recorded change costs one query."""
    if not conn.execute(text("SELECT 1 FROM phone_reading_changes WHERE case_id = :c LIMIT 1"), {"c": case_id}).first():
        return None
    links = links_added_by(conn, case_id, user_id)
    found = states(conn, case_id, links, user_id)
    waiting = [(l, found[l.id]) for l in links if found[l.id]["needs_choice"]]
    if not waiting:
        return None
    first_link, first = waiting[0]
    return {"links": len(waiting), "records": sum(s["reading_changed"]["records"] for _, s in waiting),
            "through_seq": max(s["through_seq"] for _, s in waiting), "first_kind": first_link.kind,
            "first_container": first_link.container_id, "first_words": first["reading_changed"]["items"][0]["words"],
            "at": max(i["at"] for _, s in waiting for i in s["reading_changed"]["items"])}


def _link(conn, case_id, kind, link_id):
    links = {"entry": ("SELECT l.id, l.entry_id AS container, l.target_type, l.target_id, l.source_anchor, l.created_at, "
                       "l.created_by_user_id AS adder, l.target_label AS label FROM workspace_entry_links l WHERE "
                       "l.case_id = :c AND l.id = :i"),
             "dossier": ("SELECT l.id, l.dossier_id AS container, l.target_type, l.target_id, l.source_anchor, "
                         "l.created_at, l.created_by_user_id AS adder, l.label FROM dossier_links l WHERE l.case_id = "
                         ":c AND l.id = :i"),
             "assessment": ("SELECT l.id, a.dossier_id AS container, l.target_type, l.target_id, l.source_anchor, "
                            "l.created_at, a.author_user_id AS adder, l.label FROM dossier_assessment_links l JOIN "
                            "dossier_assessments a ON a.id = l.assessment_id WHERE l.case_id = :c AND l.id = :i")}
    if kind not in links:
        raise LinkStateError("That is not a kind of link.")
    r = conn.execute(text(links[kind]), {"c": case_id, "i": link_id}).first()
    if r is None:
        raise Missing("This link is no longer here.")
    return Link(kind, str(r.id), str(r.container), r.target_type, r.target_id, _anchor(r.source_anchor), r.created_at,
                str(r.adder) if r.adder else None, None, r.label)


def choose(db, *, case_id, link_kind, link_id, choice, through_seq, user, expected_version=None) -> dict:
    """Keep or Remove by the person who added the link, once a reading changed. Keep leaves the link as it is. Remove
    goes through the link's own removal path, which keeps its record. The choice is one more row, with who and when."""
    from services import dossier_service, manual_changes, workspace_entry_service
    if choice not in ("keep", "remove"):
        raise LinkStateError("The choice is Keep or Remove.")
    conn = db.connection()
    link = _link(conn, case_id, link_kind, link_id)
    state = states(conn, case_id, [link], user.id)[link.id]
    if not state["needs_choice"]:
        raise Changed("Nothing here is waiting for a choice any more.")
    if state["through_seq"] != through_seq:
        raise Changed("The reading changed again while you were looking. The new change is shown. Your choice was not "
                      "saved. Choose again.")
    if not state["can_choose"]:
        raise NotYours("Keep or Remove is offered to the person who added this link.")
    if choice == "remove" and not state["can_remove"]:
        raise LinkStateError("A link that supports an assessment is removed by removing that assessment.")
    rid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO phone_link_choices (id, case_id, link_kind, link_id, container_id, target_type, target_id, choice, "
        "through_seq, records_affected, chosen_by_user_id, chosen_by) VALUES (:i, :c, :k, :l, :o, :t, :ti, :ch, :s, :n, "
        ":u, :b)"), {"i": rid, "c": case_id, "k": link.kind, "l": link.id, "o": link.container_id, "t": link.target_type,
                     "ti": link.target_id, "ch": choice, "s": through_seq, "n": state["reading_changed"]["records"],
                     "u": user.id, "b": user.name})
    reason = "%s after the reading of %s changed" % ("Kept" if choice == "keep" else "Removed",
                                                     "%d record%s" % (state["reading_changed"]["records"],
                                                                      "" if state["reading_changed"]["records"] == 1
                                                                      else "s"))
    manual_changes.record_change(db, "phone_link_choice", case_id, {"type": "%s_link" % link.kind, "id": link.id},
                                 {"link": "reading changed"}, {"link": choice}, user, reason,
                                 link="/cases/%s/workspace" % case_id, change_type="confirm" if choice == "keep"
                                 else "change", pattern_key=manual_changes.make_pattern_key("phone_link_choice", choice))
    if choice == "keep":
        db.commit()
    elif link.kind == "dossier":
        dossier_service.remove_link(db, dossier_id=uuid.UUID(link.container_id), link_id=uuid.UUID(link.id), user=user)
    else:
        workspace_entry_service.remove_entry_link(db, case_id=case_id, entry_id=uuid.UUID(link.container_id),
                                                  link_id=uuid.UUID(link.id), current_user=user,
                                                  expected_version=expected_version)
    return {"id": str(rid), "choice": choice, "by": user.name, "link_id": link.id,
            "removed": choice == "remove"}


# ---- exports ---------------------------------------------------------------------------------------------------------

def export_notes(conn, case_id, selection_id) -> dict:
    """``{record_uid: [words]}`` for a frozen selection the export draws: the state of the links it was gathered from
    (``collected_from``: a finding or a dossier), or of the links holding this selection itself. The full list, never
    clipped."""
    row = conn.execute(text("SELECT collected_from FROM phone_selections WHERE id::text = :s AND case_id = :c"),
                       {"s": str(selection_id), "c": case_id}).first()
    if row is None:
        return {}
    source = _anchor(row.collected_from)
    if source.get("container") == "entry":
        links = entry_links(conn, case_id, source["id"])
    elif source.get("container") == "dossier":
        links = dossier_links(conn, case_id, source["id"])
    else:
        held = source.get("selection") or selection_id
        links = [l for kind_sql in (("entry", "workspace_entry_links", "entry_id", "target_label"),
                                    ("dossier", "dossier_links", "dossier_id", "label"))
                 for l in _holding(conn, case_id, held, *kind_sql)]
    if not links:
        return {}
    _expand(conn, case_id, links)
    bulk = _bulk(conn, case_id, links)
    notes = defaultdict(list)
    for link in links:
        changes = [r for u in link.records for r in bulk["changes"].get(u, ())]
        reading = sorted(_reading_items(link, changes).values(), key=lambda i: (i["record_uid"], i["field"]))
        for item in reading:
            notes[item["record_uid"]].append("Reading changed since collected. " + item["words"])
        for uid in link.records:
            for item in _corrected_items(link, bulk["corrections"].get(uid, ()), bulk["masked"]):
                notes[uid].append("Corrected since collected. " + item["words"])
        if link.target_type == "phone_record" and str(link.target_id).lower() in bulk["aside"]:
            notes[str(link.target_id).lower()].append(SET_ASIDE)
        keep = next((c for c in reversed(bulk["choices"].get(link.id, ())) if c.choice == "keep"), None)
        if keep and reading:
            for uid in {i["record_uid"] for i in reading}:
                notes[uid].append("Kept by %s on %s." % (keep.chosen_by, _day(keep.chosen_at)))
    return {uid: list(dict.fromkeys(words)) for uid, words in notes.items()}


def _holding(conn, case_id, selection_id, kind, table, column, label) -> list:
    return [Link(kind, str(r.id), str(r.container), "phone_selection", r.target_id, _anchor(r.source_anchor), r.created_at,
                 None, None, r.label) for r in conn.execute(text(
                     "SELECT id, %s AS container, target_id, source_anchor, created_at, %s AS label FROM %s WHERE "
                     "case_id = :c AND target_type = 'phone_selection' AND target_id = :s" % (column, label, table)),
                     {"c": case_id, "s": str(selection_id)})]
