"""Text places: written places of phone records placed on the map by a person (04 section 6.5).

A calendar location, a check-in's place name or a Location's written address on a record that carries no coordinate
is resolved to a position only by a person: they choose a point and radius on the map with a reason, recorded in the
case decision ledger with them as Actor (``place``; ``remove`` reverses it). The offline GeoNames lookup
(``services.geocoder.forward_candidates``) may suggest candidates; a suggestion is shown as "suggested, not
confirmed" and is never saved by itself. When the person starts from one, the placement keeps which candidate it was,
and the point and radius saved are still the ones the person submitted.

A placement becomes a place observation of the phone (``source_kind = 'person_placed'``, ``radius_basis =
'manual'``) with the kind ``places.classify_point`` gives the record (planned for a calendar entry, declared for a
check-in), and never presence: a written place says where the text points, not where the phone was. Observations are
rewritten from the current placements on every placement and removal and on every projection rebuild
(``project``), and ``pol_projection_state.text_places_version`` is raised each time a person changes one.

The text is the record's effective text (a person's correction of it, else what the phone recorded); the text as it
stood when the person placed it is kept on the placement, and the phone's own text stays beside it.
"""
from __future__ import annotations

import json
import logging
import uuid
from types import SimpleNamespace

from sqlalchemy import text

from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
from services.financial import decisions
from services.pattern_of_life import activity, places

log = logging.getLogger(__name__)

PAGE = 200
MAX_RADIUS_M = 50000
SOURCE_KIND = "person_placed"
NEVER_PRESENCE = "declared"

# (model type, field name) -> group. A Location's Name is a place only when the record is not a media location (its
# Name is then the file's name). A SocialMediaActivity's Title is a place only on a check-in.
FIELDS = {
    ("CalendarEntry", "Location"): "calendar",
    ("SocialMediaActivity", "Title"): "checkin",
    ("Location", "PositionAddress"): "other",
    ("Location", "Description"): "other",
    ("Location", "Name"): "other",
}
GROUP_WORDS = {"calendar": "Calendar location", "checkin": "Check-in place", "other": "Written place"}
KIND_WORDS = {"planned": "Planned (calendar)", "declared": "Declared (written, not a visit)",
              "searched": "Searched (looked up, not visited)"}
END_FIELDS = ("EndDate", "EndTime", "DateEnded", "To")
# Never the time a written place stands for: when a recurrence stops.
NOT_START_FIELDS = ("RepeatUntil",)
# When no time of the record is marked its event time, these name its start, in this order, before any other time.
START_FIELDS = ("StartDate", "StartTime", "TimeStamp", "Date", "DateStarted", "From")


class TextPlaceError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ---- suggestion policy (6.5) ----------------------------------------------------------------------------------------

def suggestion_status(primary=None, fallback=None) -> dict:
    """``{"enabled", "reason", "places"}``. Suggestions read only the GeoNames index on this server; they are off when
    a configured geocoder backend is not in house (the deployment has chosen a service outside, 6.5) or the index is
    not installed. No backend configured counts as in house: nothing is configured to leave the server."""
    from services import geocoder
    backends = [b for b in ((primary, fallback) if (primary or fallback) else
                            (getattr(geocoder, "_PRIMARY", None), getattr(geocoder, "_FALLBACK", None))) if b]
    if backends:
        st = places.reverse_geocoding_status(*backends)
        if not st["enabled"]:
            return {"enabled": False, "places": 0,
                    "reason": "Suggestions are off: the configured %s geocoder is not on this server's own network."
                              % ", ".join(b.name for b in backends)}
    src = geocoder.forward_source()
    if not src["available"]:
        return {"enabled": False, "places": 0, "reason": "Suggestions are off: " + src["reason"]}
    return {"enabled": True, "places": src["places"],
            "reason": "Suggested from the GeoNames place list on this server (%s towns and cities of 1,000 people or "
                      "more). Nothing is sent outside." % format(src["places"], ",")}


# ---- the list -------------------------------------------------------------------------------------------------------

_CANDIDATES = """
SELECT t.extraction_id, t.record_uid, t.document_index, t.ordinal, t.model_type, t.field_name, t.field_path,
       t.value AS phone_text, t.effective_value AS place_text
FROM phone_texts t
JOIN phone_interpretation_state s ON s.extraction_id = t.extraction_id AND s.generation = t.generation
JOIN phone_extractions x ON x.id = t.extraction_id AND x.standing = 'active'
WHERE t.case_id = :c AND (CAST(:e AS uuid) IS NULL OR t.extraction_id = CAST(:e AS uuid))
  AND t.value_index = 0 AND NOT t.is_sensitive AND btrim(t.effective_value) <> ''
  AND (t.model_type, t.field_name) IN (('CalendarEntry', 'Location'), ('SocialMediaActivity', 'Title'),
       ('Location', 'PositionAddress'), ('Location', 'Description'), ('Location', 'Name'))
  AND NOT EXISTS (SELECT 1 FROM phone_location_points p WHERE p.extraction_id = t.extraction_id AND
                  p.generation = t.generation AND p.record_uid = t.record_uid)
  AND NOT (t.model_type = 'Location' AND EXISTS (
        SELECT 1 FROM phone_texts m WHERE m.extraction_id = t.extraction_id AND m.generation = t.generation AND
        m.record_uid = t.record_uid AND m.field_name = 'Category' AND m.value = 'Media Locations'))
"""


def _key(r):
    return (str(r.extraction_id), int(r.document_index), int(r.ordinal))


def _record_fields_many(conn, rows, wanted) -> dict:
    """(extraction_id, document_index, ordinal) -> the wanted field values of each row's record, one query per phone
    rather than one per record."""
    out, by_ext = {}, {}
    for r in rows:
        by_ext.setdefault(str(r.extraction_id), set()).add((int(r.document_index), int(r.ordinal)))
    for ext, keys in by_ext.items():
        d, o = zip(*sorted(keys))
        for di, oi, body in conn.execute(text(
                "SELECT r.document_index, r.ordinal, r.body FROM phone_records r JOIN unnest(CAST(:d AS int[]), "
                "CAST(:o AS int[])) AS k(d, o) ON r.document_index = k.d AND r.ordinal = k.o "
                "WHERE r.extraction_id = CAST(:e AS uuid)"), {"e": ext, "d": list(d), "o": list(o)}):
            if body is not None:
                out[(ext, int(di), int(oi))] = activity._field_values(body, set(wanted))
    return out


def _record_fields(conn, extraction_id, document_index, ordinal, wanted):
    r = SimpleNamespace(extraction_id=extraction_id, document_index=document_index, ordinal=ordinal)
    return _record_fields_many(conn, [r], wanted).get(_key(r), {})


def _candidates(conn, case_id, extraction_id=None) -> list:
    rows = list(conn.execute(text(_CANDIDATES + " ORDER BY t.extraction_id, t.document_index, t.ordinal, "
                                                "t.field_path"), {"c": case_id, "e": extraction_id}))
    social = [r for r in rows if r.model_type == "SocialMediaActivity"]
    types = _record_fields_many(conn, social, ("SocialActivityType",)) if social else {}
    return [r for r in rows if r.model_type != "SocialMediaActivity" or
            activity._first(types.get(_key(r), {}).get("SocialActivityType")) == "CheckIn"]


def location_fields(conn, rows) -> dict:
    """The Type and Category of every Location among ``rows``, read in one query per phone (for ``kind_of``)."""
    locs = [r for r in rows if r.model_type == "Location"]
    return _record_fields_many(conn, locs, ("Type", "Category")) if locs else {}


def kind_of(conn, r, fields=None) -> str:
    """The observation kind of a placed text: what ``classify_point`` says of the record, never presence. ``fields``
    is ``location_fields`` read for many rows at once; without it the record is read here."""
    facts = {"fields": {}}
    if r.model_type == "Location":
        facts["fields"] = (fields.get(_key(r), {}) if fields is not None else
                           _record_fields(conn, r.extraction_id, r.document_index, r.ordinal, ("Type", "Category")))
    kind = places.classify_point(r.model_type, None, None, facts, [])[0]
    return kind if kind in ("planned", "declared", "searched") else NEVER_PRESENCE


def _times(conn, extraction_id, record_uids, zones) -> dict:
    """record_uid -> (start, end, semantics, offset status) from the record's own time values."""
    out = {}
    if not record_uids:
        return out
    for r in conn.execute(text(
            "SELECT v.record_uid, v.field_name, v.effective_instant, v.local_wall_time, v.offset_state, v.semantics, "
            "v.instant_basis, v.is_event_time FROM phone_time_values v JOIN phone_interpretation_state s ON "
            "s.extraction_id = v.extraction_id AND s.generation = v.generation WHERE v.extraction_id = :e AND "
            "v.record_uid = ANY(:u) AND v.value_index = 0 ORDER BY v.record_uid, v.is_event_time DESC, "
            "array_position(CAST(:sf AS text[]), v.field_name) NULLS LAST, v.effective_instant NULLS LAST"),
            {"e": extraction_id, "u": list(record_uids), "sf": list(START_FIELDS)}):
        if r.field_name in NOT_START_FIELDS:
            continue
        inst, _, ostat = activity._instant(r, zones.get(str(extraction_id)))
        if inst is None:
            continue
        cur = out.setdefault(r.record_uid, {"start": None, "end": None, "sem": None, "os": None})
        if r.field_name in END_FIELDS:
            cur["end"] = cur["end"] or inst
        elif cur["start"] is None:
            cur.update(start=inst, sem=r.semantics or "unknown", os=ostat)
    return {k: (v["start"], max(v["start"], v["end"] or v["start"]), v["sem"], v["os"])
            for k, v in out.items() if v["start"] is not None}


def _zones(conn, extraction_ids) -> dict:
    return {str(e): activity._zone(z) for e, z in conn.execute(text(
        "SELECT extraction_id, device_zone FROM phone_interpretation_state WHERE extraction_id = ANY(:e)"),
        {"e": list(extraction_ids)})} if extraction_ids else {}


def current(conn, case_id, keys=None) -> dict:
    """(record_uid, field_path) -> the current placement row."""
    rows = conn.execute(text(
        "SELECT id, extraction_id, record_uid, field_path, model_type, place_text, lat, lon, radius_m, reason, "
        "suggestion, decision_id, actor_name, actor_email, created_at FROM pol_text_place WHERE case_id = :c AND "
        "removed_decision_id IS NULL"), {"c": case_id})
    out = {(r.record_uid, r.field_path): dict(r._mapping) for r in rows}
    return {k: v for k, v in out.items() if keys is None or k in keys}


def list_places(conn, case_id, *, extraction_id=None, status="all", cursor=0, limit=PAGE) -> dict:
    """Every text place of the case's active phones with no coordinate, placed or not, paged with true totals."""
    if status not in ("all", "placed", "not_placed"):
        raise TextPlaceError("status is all, placed or not_placed.")
    cands = _candidates(conn, case_id, extraction_id)
    every = cands
    placed = current(conn, case_id)
    counts = {"calendar": 0, "checkin": 0, "other": 0}
    for r in cands:
        counts[FIELDS[(r.model_type, r.field_name)]] += 1
    n_placed = sum(1 for r in cands if (r.record_uid, r.field_path) in placed)
    if status == "placed":
        cands = [r for r in cands if (r.record_uid, r.field_path) in placed]
    elif status == "not_placed":
        cands = [r for r in cands if (r.record_uid, r.field_path) not in placed]
    page = cands[cursor:cursor + limit]
    zones = _zones(conn, {r.extraction_id for r in page})
    times = {}
    for e in {r.extraction_id for r in page}:
        times.update(_times(conn, e, [r.record_uid for r in page if r.extraction_id == e], zones))
    kinds = location_fields(conn, page)
    history_n = dict(conn.execute(text(
        "SELECT subject_id::text || '|' || (after ->> 'field'), count(*) FROM adjudications WHERE case_id = :c AND "
        "subject_type = 'phone_record' AND decision IN ('place_text_place', 'remove_text_place') GROUP BY 1"),
        {"c": case_id}).all())
    items = []
    for r in page:
        group = FIELDS[(r.model_type, r.field_name)]
        kind = kind_of(conn, r, kinds)
        t = times.get(r.record_uid)
        p = placed.get((r.record_uid, r.field_path))
        items.append({
            "extraction_id": r.extraction_id, "record_uid": r.record_uid, "field_path": r.field_path,
            "model_type": r.model_type, "group": group, "group_words": GROUP_WORDS[group], "kind": kind,
            "kind_words": KIND_WORDS[kind], "place_text": r.place_text, "phone_text": r.phone_text,
            "corrected": r.place_text != r.phone_text,
            "start_utc": t[0] if t else None, "end_utc": t[1] if t else None,
            "placement": _view(p) if p else None,
            "decisions": int(history_n.get("%s|%s" % (r.record_uid, r.field_path), 0)),
        })
    total = len(cands)
    nxt = cursor + len(page)
    stale = no_longer_applies(conn, case_id, placed, extraction_id, every)
    return {"total": total, "returned": len(page), "cursor": cursor, "limit": limit,
            "next_cursor": nxt if nxt < total else None, "items": items,
            "counts": {"all": sum(counts.values()), "placed": n_placed, "not_placed": sum(counts.values()) - n_placed,
                       "by_group": counts, "no_longer_applies": len(stale)},
            "no_longer_applies": stale,
            "status": status, "suggestions": suggestion_status()}


def no_longer_applies(conn, case_id, placed=None, extraction_id=None, candidates=None) -> list:
    """Current placements whose written place is no longer a text place of the case: the record gained a coordinate,
    its text was corrected to blank, or its phone was superseded. They give no observation; they are listed (never
    paged away) so a person can see and remove them."""
    placed = current(conn, case_id) if placed is None else placed
    mine = {k: p for k, p in placed.items() if extraction_id is None or str(p["extraction_id"]) == str(extraction_id)}
    if not mine:
        return []
    rows = _candidates(conn, case_id, extraction_id) if candidates is None else candidates
    live = {(r.record_uid, r.field_path) for r in rows}
    out = []
    for (uid, fp), p in sorted(mine.items(), key=lambda kv: (str(kv[1]["created_at"]), str(kv[0][0]))):
        if (uid, fp) in live:
            continue
        out.append(dict(_view(p), extraction_id=p["extraction_id"], record_uid=uid, field_path=fp,
                        model_type=p["model_type"],
                        reason_words="This placement no longer applies: the record now has a position, its text is "
                                     "blank, or its phone report is no longer the one the case stands on. It is not "
                                     "on the map; remove it to close it."))
    return out


def _view(p):
    return {k: p[k] for k in ("id", "lat", "lon", "radius_m", "reason", "suggestion", "decision_id", "actor_name",
                              "created_at", "place_text")}


# ---- one record -----------------------------------------------------------------------------------------------------

def _target(conn, case_id, record_uid, field_path):
    for r in _candidates(conn, case_id):
        if str(r.record_uid) == str(record_uid) and r.field_path == field_path:
            return r
    placed = current(conn, case_id).get((uuid.UUID(str(record_uid)), field_path))
    if placed:
        raise TextPlaceError("This record now carries a coordinate or is no longer in the case's active phones; "
                             "its placement can only be removed.", 409)
    raise TextPlaceError("That written place is not among this case's text places.", 404)


def suggest(conn, case_id, record_uid, field_path) -> dict:
    """GeoNames candidates for one text place, labelled as suggestions. Reads the text itself, so no case text travels
    in a request."""
    st = suggestion_status()
    r = _target(conn, case_id, record_uid, field_path)
    if not st["enabled"]:
        return {"enabled": False, "reason": st["reason"], "total": 0, "returned": 0, "candidates": []}
    from services import geocoder
    try:
        out = geocoder.forward_candidates(r.place_text)
    except LookupError as exc:
        return {"enabled": False, "reason": "Suggestions are off: %s" % exc, "total": 0, "returned": 0,
                "candidates": []}
    return dict(out, enabled=True, reason=st["reason"], label="Suggested, not confirmed")


def _place_snapshot(p):
    """As the decision ledger holds it: coordinates as decimal strings to 7 places, the radius in whole metres."""
    if p is None:
        return None
    return {"lat": "%.7f" % p["lat"], "lon": "%.7f" % p["lon"], "radius_m": int(round(p["radius_m"]))}


def _subject(session, case_id, r):
    from postgres.models.phone_identity import PhoneRecordSubject
    s = session.get(PhoneRecordSubject, r.record_uid)
    if s is None:
        s = PhoneRecordSubject(id=r.record_uid, case_id=case_id, extraction_id=r.extraction_id,
                               document_index=r.document_index, ordinal=r.ordinal)
        session.add(s)
        session.flush()
    return s


def _sug_snapshot(sug):
    """The ledger refuses floats in a snapshot, so a suggestion is held there as strings."""
    return {k: (str(v) if v is not None else None) for k, v in sug.items()} if sug else None


def _clean_suggestion(sug):
    if sug is None:
        return None
    if not isinstance(sug, dict):
        raise TextPlaceError("The suggestion is not one the list offered.")
    keep = {k: sug.get(k) for k in ("geonameid", "name", "country_code", "admin1", "lat", "lon", "population")}
    if keep["geonameid"] is None or not keep["name"]:
        raise TextPlaceError("The suggestion is not one the list offered.")
    try:
        keep["lat"] = "%.5f" % float(keep["lat"]) if keep["lat"] is not None else None
        keep["lon"] = "%.5f" % float(keep["lon"]) if keep["lon"] is not None else None
    except (TypeError, ValueError):
        raise TextPlaceError("The suggestion is not one the list offered.")
    keep["source"] = "GeoNames (offline)"
    keep["basis"] = "suggested by the offline place list; the point and radius are the person's"
    return keep


def _offered(r, sug):
    """The suggestion as this server offers it for the record's text now, or a refusal: a placement keeps only a
    candidate the list really offered for that text (its name and point taken from the list, not the request)."""
    if sug is None:
        return None
    from services import geocoder
    if not suggestion_status()["enabled"]:
        raise TextPlaceError("Suggestions are off on this server, so a suggestion cannot be kept with the place.")
    try:
        offered = geocoder.forward_candidates(r.place_text)["candidates"]
    except LookupError:
        raise TextPlaceError("Suggestions are off on this server, so a suggestion cannot be kept with the place.")
    for c in offered:
        if str(c["geonameid"]) == str(sug["geonameid"]):
            return _clean_suggestion(c)
    raise TextPlaceError("The suggestion is not one the list offered for this text.")


def place(session, case_id, record_uid, field_path, *, lat, lon, radius_m, reason, actor, suggestion=None):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise TextPlaceError("The point is not on the map.")
    if radius_m != int(radius_m) or not (1 <= radius_m <= MAX_RADIUS_M):
        raise TextPlaceError("The radius is whole metres, from 1 m to 50,000 m.")
    radius_m = int(radius_m)
    if not isinstance(reason, str) or not reason.strip():
        raise TextPlaceError("Say why the place is here.")
    conn = session.connection()
    r = _target(conn, case_id, record_uid, field_path)
    sug = _offered(r, _clean_suggestion(suggestion))
    old = current(conn, case_id).get((r.record_uid, r.field_path))
    after = {"place": _place_snapshot({"lat": lat, "lon": lon, "radius_m": radius_m}), "field": r.field_path,
             "suggestion": _sug_snapshot(sug), "text": r.place_text}
    before = {"place": _place_snapshot(old), "field": r.field_path,
              "suggestion": _sug_snapshot(old["suggestion"]) if old else None,
              "text": old["place_text"] if old else None}
    if before == after:
        raise TextPlaceError("This written place is already placed here with that radius.", 409)
    row = decisions.record(session, case_id=case_id, subject=_subject(session, case_id, r),
                           subject_type=AdjudicationSubject.phone_record,
                           decision=AdjudicationDecision.place_text_place, reason=reason.strip(), actor=actor,
                           before=before, after=after)
    if old:
        conn.execute(text("UPDATE pol_text_place SET removed_decision_id = :d WHERE id = :i"),
                     {"d": row.id, "i": old["id"]})
    pid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO pol_text_place (id, case_id, extraction_id, record_uid, field_path, model_type, place_text, lat, "
        "lon, radius_m, reason, suggestion, decision_id, actor_name, actor_email) VALUES (:i, :c, :e, :u, :f, :m, :t, "
        ":la, :lo, :r, :re, CAST(:s AS jsonb), :d, :an, :ae)"),
        {"i": pid, "c": case_id, "e": r.extraction_id, "u": r.record_uid, "f": r.field_path, "m": r.model_type,
         "t": r.place_text, "la": lat, "lo": lon, "r": radius_m, "re": reason.strip(),
         "s": json.dumps(sug) if sug else None, "d": row.id, "an": actor.name, "ae": actor.email})
    project(conn, r.extraction_id, bump=True)
    _feed(session, case_id, r.record_uid, r.field_path, _place_snapshot(old), after["place"], actor, reason.strip(),
          bool(sug))
    return {"placement_id": str(pid), "decision_id": str(row.id),
            "replaced_placement_id": str(old["id"]) if old else None}


def remove(session, case_id, record_uid, field_path, *, reason, actor):
    if not isinstance(reason, str) or not reason.strip():
        raise TextPlaceError("Say why the place is removed.")
    conn = session.connection()
    old = current(conn, case_id).get((uuid.UUID(str(record_uid)), field_path))
    if old is None:
        raise TextPlaceError("That written place has not been placed.", 409)
    from postgres.models.phone_identity import PhoneRecordSubject
    subject = session.get(PhoneRecordSubject, old["record_uid"])
    row = decisions.record(session, case_id=case_id, subject=subject, subject_type=AdjudicationSubject.phone_record,
                           decision=AdjudicationDecision.remove_text_place, reason=reason.strip(), actor=actor,
                           before={"place": _place_snapshot(old), "field": field_path, "text": old["place_text"]},
                           after={"place": None, "field": field_path, "text": old["place_text"]})
    conn.execute(text("UPDATE pol_text_place SET removed_decision_id = :d WHERE id = :i"),
                 {"d": row.id, "i": old["id"]})
    project(conn, old["extraction_id"], bump=True)
    _feed(session, case_id, old["record_uid"], field_path, _place_snapshot(old), None, actor, reason.strip(), False)
    return {"decision_id": str(row.id), "removed_placement_id": str(old["id"])}


def history(conn, case_id, record_uid, field_path) -> list:
    """Every placement of the written place, oldest first, with the decision that ended each and the text as it
    stood when it was placed."""
    return [dict(r._mapping) for r in conn.execute(text(
        "SELECT p.id, p.place_text, p.lat, p.lon, p.radius_m, p.reason, p.suggestion, p.decision_id, "
        "p.removed_decision_id, p.actor_name, p.created_at, e.decision AS ended_by, e.reason AS ended_reason, "
        "e.actor_name AS ended_actor_name, e.created_at AS ended_at FROM pol_text_place p "
        "LEFT JOIN adjudications e ON e.id = p.removed_decision_id "
        "WHERE p.case_id = :c AND p.record_uid = :u AND p.field_path = :f ORDER BY p.created_at, p.id"),
        {"c": case_id, "u": record_uid, "f": field_path})]


# ---- the projection -------------------------------------------------------------------------------------------------

def project(conn, extraction_id, bump=False) -> dict:
    """Rewrite the extraction's person-placed observations from its current placements (no commit). A placement whose
    record now has a coordinate, or is no longer a text place of the current interpretation, gives no observation
    and is counted."""
    conn.execute(text("DELETE FROM pol_place_observation WHERE extraction_id = :e AND source_kind = :s"),
                 {"e": extraction_id, "s": SOURCE_KIND})
    st = activity.current_generation(conn, extraction_id)
    stats = {"placed": 0, "not_projected": 0, "no_time": 0}
    if st is not None and st.generation:
        rows = conn.execute(text(
            "SELECT id, record_uid, field_path, model_type, lat, lon, radius_m, decision_id FROM pol_text_place "
            "WHERE extraction_id = :e AND removed_decision_id IS NULL"), {"e": extraction_id}).all()
        if rows:
            cands = {(r.record_uid, r.field_path): r for r in _candidates(conn, st.case_id, extraction_id)}
            kinds = location_fields(conn, [cands[(p.record_uid, p.field_path)] for p in rows
                                           if (p.record_uid, p.field_path) in cands])
            times = _times(conn, extraction_id, [p.record_uid for p in rows],
                           {str(extraction_id): activity._zone(st.device_zone)})
            out = []
            for p in rows:
                c = cands.get((p.record_uid, p.field_path))
                if c is None:
                    stats["not_projected"] += 1
                    continue
                t = times.get(p.record_uid)
                if t is None:
                    stats["no_time"] += 1
                    continue
                out.append({"c": st.case_id, "e": extraction_id, "ru": p.record_uid, "rt": p.model_type[:64],
                            "k": kind_of(conn, c, kinds), "sk": SOURCE_KIND, "lat": p.lat, "lon": p.lon,
                            "rad": float(p.radius_m), "rep": None, "rb": "manual", "s": t[0], "en": t[1],
                            "os": t[3], "sem": t[2], "pb": None,
                            "fl": [] if t[3] == "explicit" else ["offset_absent"], "app": None,
                            "fp": p.field_path, "dec": p.decision_id})
                stats["placed"] += 1
            if out:
                conn.execute(text(
                    "INSERT INTO pol_place_observation (case_id, extraction_id, record_uid, record_type, kind, "
                    "source_kind, lat, lon, radius_m, radius_reported, radius_basis, start_utc, end_utc, offset_status, "
                    "time_semantics, presence_basis, attribution_flags, source_app, field_path, decision_id) VALUES "
                    "(:c, :e, :ru, :rt, :k, :sk, :lat, :lon, :rad, :rep, :rb, :s, :en, :os, :sem, :pb, :fl, :app, "
                    ":fp, :dec)"), out)
    if bump:
        conn.execute(text("UPDATE pol_projection_state SET text_places_version = text_places_version + 1 "
                          "WHERE extraction_id = :e"), {"e": extraction_id})
    return stats


def _feed(session, case_id, record_uid, field_path, before, after, actor, reason, from_suggestion):
    from services import manual_changes
    manual_changes.record_change(session, "pattern_text_place", case_id,
                                 {"type": "phone_record", "id": str(record_uid)}, {"place": before},
                                 {"place": after, "from_suggestion": from_suggestion}, actor, reason,
                                 field=field_path, link="/cases/%s/phone-patterns" % case_id,
                                 pattern_key=manual_changes.make_pattern_key("pattern_text_place", field_path),
                                 source="phone")
