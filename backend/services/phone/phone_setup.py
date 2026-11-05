"""What a phone's setup decisions hold and what each would change (03 section 7.3, 07 section 5).

``state`` is the Needs a decision box's data: the region, device zone, zone for times with no offset and clock
offsets in effect, each with its basis and who decided it. ``describe`` answers before saving: it counts what the
proposed value would change from this phone's own rows, by the same parsers the re-read uses, and saves nothing.
Saving is ``corrections``; the re-read is the sweep.
"""
from __future__ import annotations

from sqlalchemy import text

from services.phone import corrections, identifiers, numbers, time_display as T
from services.phone.mappings import apply

BARE = "region_basis IS NOT NULL AND region_basis <> 'explicit_plus'"


def _generation(conn, extraction_id):
    return conn.execute(text("SELECT generation FROM phone_interpretation_state WHERE extraction_id = :e"),
                        {"e": extraction_id}).scalar() or 0


def bare_numbers(conn, extraction_id) -> list:
    """``(as written, identity key, was read)`` of each number this phone's current reading holds without +: read
    under the region (``region_basis`` set), or digits that were no valid number there (``other:digits:``)."""
    return conn.execute(text(
        "SELECT DISTINCT identifier_raw, identity_key, identity_key LIKE 'phone:%' FROM phone_participations WHERE "
        "extraction_id = :e AND generation = :g AND " + BARE + " UNION SELECT DISTINCT identifier_raw, identity_key, "
        "identity_key LIKE 'phone:%' FROM phone_identity_sightings WHERE extraction_id = :e AND generation = :g AND "
        + BARE), {"e": extraction_id, "g": _generation(conn, extraction_id)}).fetchall()


def _decision(row):
    if row is None:
        return None
    return {"id": str(row.id), "by": row.actor_name, "at": T.iso(row.created_at), "reason": row.reason}


def region_sentence(count, region, basis) -> str:
    name = numbers.region_name(region)
    noun = "number was" if count == 1 else "numbers were"
    how = {"decided": " (a person's decision on this phone)", "case_setting": " (the case setting)"}.get(basis, "")
    return "%s %s read assuming %s%s" % ("{:,}".format(count), noun, name, how)


def region_state(conn, extraction_id) -> dict:
    region, basis = apply.default_region(conn, extraction_id)
    r = corrections._latest(conn, extraction_id, "set_phone_default_region")
    bare = bare_numbers(conn, extraction_id)
    count = len({r[1] for r in bare if r[2]})
    return {"region": region, "name": numbers.region_name(region), "basis": basis, "assumed": basis != "decided",
            "numbers": count, "words": region_sentence(count, region, basis),
            "unread": len({r[1] for r in bare if not r[2]}),
            "decision": _decision(r) if basis == "decided" else None, "undo_to": ((r.before or {}).get("default_region")
                                                                                 if r and basis == "decided" else None)}


def _zone_words(zone):
    return T.zone_name(zone) if zone and T.valid_zone(zone) else zone


def zone_state(conn, extraction_id) -> dict:
    x = conn.execute(text("SELECT device_zone, device_zone_basis, examiner_zone FROM pv_extraction WHERE extraction_id "
                          "= :e"), {"e": extraction_id}).first()
    report = conn.execute(text("SELECT device_zone FROM phone_extractions WHERE id = :e"), {"e": extraction_id}).scalar()
    r = corrections._latest(conn, extraction_id, "set_phone_device_zone")
    decided = (r.after or {}).get("device_zone") if r else None
    return {"zone": x.device_zone if x else None, "name": _zone_words(x.device_zone) if x else None,
            "basis": x.device_zone_basis if x else None, "report_zone": report, "examiner_zone": x.examiner_zone if x else None,
            "decided": decided, "decision": _decision(r) if decided else None,
            "undo_to": (r.before or {}).get("device_zone") if r and decided else None}


def offsetless_state(conn, extraction_id) -> dict:
    g = _generation(conn, extraction_id)
    no_offset, applied = conn.execute(text(
        "SELECT count(*), count(*) FILTER (WHERE effective_instant IS NOT NULL) FROM phone_time_values WHERE "
        "extraction_id = :e AND generation = :g AND instant IS NULL AND local_wall_time IS NOT NULL"),
        {"e": extraction_id, "g": g}).one()
    r = corrections._latest(conn, extraction_id, "apply_phone_zone_to_offsetless")
    zone = (r.after or {}).get("offsetless_zone") if r else None
    return {"times": int(no_offset), "applied": int(applied), "zone": zone, "name": _zone_words(zone),
            "decision": _decision(r) if zone else None, "undo_to": (r.before or {}).get("offsetless_zone") if r and zone else None}


def clock_state(conn, extraction_id) -> dict:
    periods = []
    who = {r[0]: r for r in conn.execute(text(
        "SELECT id, actor_name, created_at, reason FROM adjudications WHERE subject_type = 'phone_extraction' AND "
        "subject_id = :e AND decision = 'set_phone_clock_offset'"), {"e": extraction_id})}
    g = _generation(conn, extraction_id)
    for (start, end), (secs, did) in corrections._offset_periods(conn, extraction_id).items():
        if not secs:
            continue
        d = who[did]
        periods.append({"offset_seconds": secs, "start": start, "end": end, "times": _times_in(conn, extraction_id, g, start, end),
                        "decision": {"id": str(d[0]), "by": d[1], "at": T.iso(d[2]), "reason": d[3]}})
    return {"periods": periods}


def state_exists(conn, case_id, extraction_id):
    if not conn.execute(text("SELECT 1 FROM phone_extractions WHERE id = :e AND case_id = :c"),
                        {"e": extraction_id, "c": case_id}).scalar():
        raise corrections.CorrectionError("That phone is not in this case.")


def state(conn, case_id, extraction_id) -> dict:
    state_exists(conn, case_id, extraction_id)
    return {"extraction_id": str(extraction_id), "region": region_state(conn, extraction_id),
            "zone": zone_state(conn, extraction_id), "offsetless": offsetless_state(conn, extraction_id),
            "clock": clock_state(conn, extraction_id),
            "regions": numbers.region_list()}


# ---- what a change would do ---------------------------------------------------------------------------------------

def _times_in(conn, extraction_id, generation, start, end) -> int:
    """Times the report gave an instant for inside [start, end), the rule ``effective_instant`` moves."""
    return int(conn.execute(text(
        "SELECT count(*) FROM phone_time_values WHERE extraction_id = :e AND generation = :g AND instant IS NOT NULL "
        "AND (CAST(:a AS timestamptz) IS NULL OR instant >= :a) AND (CAST(:b AS timestamptz) IS NULL OR instant < :b)"),
        {"e": extraction_id, "g": generation, "a": corrections.parse_instant(start) if start else None,
         "b": corrections.parse_instant(end) if end else None}).scalar() or 0)


def describe_region(conn, extraction_id, region) -> dict:
    """Parse every number written without + under the proposed country, as the re-read will."""
    if region not in numbers.regions():
        raise corrections.CorrectionError("Choose a country from the list.")
    now = apply.default_region(conn, extraction_id)[0]
    bare = bare_numbers(conn, extraction_id)
    changed, read, unread = set(), set(), set()  # counted as the box counts them: a number, however it was spelled
    for raw, key, _was_read in bare:
        a = identifiers.classify(raw, region=now, region_basis="decided")
        b = identifiers.classify(raw, region=region, region_basis="decided")
        if (a.identity_key if a else None) != (b.identity_key if b else None):
            changed.add(key)
        (read if b is not None and b.kind == "phone" else unread).add(b.identity_key if b else raw)
    count = len({r[1] for r in bare})
    return {"numbers": count, "changed": len(changed), "unread": len(unread), "read": len(read),
            "words": "%s numbers on this phone have no country code. Read in %s, %s of them would change and %s would "
                     "not be valid numbers there. The phone is then read again; the report itself does not change."
                     % ("{:,}".format(count), numbers.region_name(region), "{:,}".format(len(changed)),
                        "{:,}".format(len(unread)))}


def describe_device_zone(conn, extraction_id, zone) -> dict:
    if not T.valid_zone(zone):
        raise corrections.CorrectionError("Choose a time zone from the list (for example America/New_York).")
    now = zone_state(conn, extraction_id)
    return {"words": "Times on this phone would show in %s when a list is set to the phone's zone. Moments do not "
                     "move: this changes how they are shown, and the phone is read again. %s" % (
                         T.zone_name(zone), "The report recorded %s; that stays on record." % now["report_zone"]
                         if now["report_zone"] else "The report recorded no zone for this phone.")}


def describe_offsetless(conn, extraction_id, zone) -> dict:
    if not T.valid_zone(zone):
        raise corrections.CorrectionError("Choose a time zone from the list (for example America/New_York).")
    g = _generation(conn, extraction_id)
    o = offsetless_state(conn, extraction_id)
    undated = int(conn.execute(text(
        "SELECT count(*) FROM phone_comm_events WHERE extraction_id = :e AND generation = :g AND sort_instant IS NULL "
        "AND record_uid IN (SELECT record_uid FROM phone_time_values WHERE extraction_id = :e AND generation = :g AND "
        "instant IS NULL AND local_wall_time IS NOT NULL)"), {"e": extraction_id, "g": g}).scalar() or 0)
    return {"times": o["times"], "undated_events": undated,
            "words": "%s %s written with no offset would be read in %s, marked as coming from this decision. %s "
                     "messages and calls now with no time would get one. The report's own text stays beside each."
                     % ("{:,}".format(o["times"]), "time" if o["times"] == 1 else "times", T.zone_name(zone),
                        "{:,}".format(undated))}


def _amount(seconds) -> str:
    n = abs(seconds)
    parts = [("day", n // 86400), ("hour", n % 86400 // 3600), ("minute", n % 3600 // 60), ("second", n % 60)]
    return ", ".join("%d %s%s" % (v, w, "" if v == 1 else "s") for w, v in parts if v) or "0 seconds"


def describe_clock(conn, extraction_id, offset_seconds, start, end) -> dict:
    if not isinstance(offset_seconds, int) or abs(offset_seconds) > corrections.MAX_OFFSET_SECONDS or not offset_seconds:
        raise corrections.CorrectionError("The offset is a whole number of seconds, at most seven days either way.")
    if start and end and corrections.parse_instant(start) >= corrections.parse_instant(end):
        raise corrections.CorrectionError("The period must end after it starts.")
    g = _generation(conn, extraction_id)
    n = _times_in(conn, extraction_id, g, start, end)
    total = _times_in(conn, extraction_id, g, None, None)
    return {"times": n, "total": total,
            "words": "%s of this phone's %s times would move %s %s. The report's own times stay beside the adjusted "
                     "ones, and the adjusted time is used in lists, counts and searches."
                     % ("{:,}".format(n), "{:,}".format(total), _amount(offset_seconds),
                        "later" if offset_seconds > 0 else "earlier")}


# ---- times that came from a decision --------------------------------------------------------------------------------

def _has_zone_decision(conn, case_id) -> bool:
    return conn.execute(text("SELECT 1 FROM adjudications WHERE case_id = :c AND subject_type = 'phone_extraction' AND "
                             "decision = 'apply_phone_zone_to_offsetless' LIMIT 1"), {"c": case_id}).first() is not None


def zone_decided_files(conn, case_id, file_uids) -> set:
    """The given files carried by a message whose time comes from a zone decision, for Media's ``taken_or_sent``."""
    uids = [str(u) for u in file_uids]
    if not uids or not _has_zone_decision(conn, case_id):
        return set()
    return {str(r[0]) for r in conn.execute(text(
        "SELECT DISTINCT l.file_uid FROM pv_attachment_link l JOIN phone_record_summaries s ON s.record_uid = l.record_uid "
        "JOIN phone_comm_events ev ON ev.record_uid = coalesce(s.root_record_uid, l.record_uid) AND ev.generation = "
        "s.generation JOIN phone_time_values t ON t.record_uid = ev.record_uid AND t.generation = ev.generation AND "
        "t.field_name = ev.time_field WHERE l.case_id = :c AND l.file_uid = ANY(CAST(:u AS uuid[])) AND t.instant_basis "
        "= ANY(CAST(:b AS text[]))"), {"c": case_id, "u": uids, "b": list(T.ZONE_BASES)})}


def zone_decided_times(conn, case_id, record_uids) -> set:
    """``{(record_uid, field name or path)}`` of the given records whose time comes from a zone decision (02 section 4.1 rule
    2), so a list labels them as decided. No such decision in the case: no read of the time table."""
    uids = [str(u) for u in record_uids]
    if not uids or not _has_zone_decision(conn, case_id):
        return set()
    return {(str(r[0]), f) for r in conn.execute(text(
        "SELECT t.record_uid, t.field_name, t.field_path FROM phone_time_values t JOIN phone_interpretation_state s ON "
        "s.extraction_id = t.extraction_id AND s.generation = t.generation WHERE t.record_uid = ANY(CAST(:u AS uuid[])) "
        "AND t.instant_basis = ANY(CAST(:b AS text[]))"), {"u": uids, "b": list(T.ZONE_BASES)}) for f in r[1:]}
