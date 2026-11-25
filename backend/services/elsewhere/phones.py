"""The Phones part: what the case's other phones hold about the subject.

Rules, per other phone:
- a copy of the record (same kind, within two minutes, the same text; for a call or a message without text, the
  same two numbers) **agrees**; a copy deleted on one side says so;
- no copy, and the phone's owner is a party to the record: when that phone holds the conversation either side of
  the record's time, the record is **missing here**; otherwise **nothing found**, with what the phone holds;
- no copy, and the owner is not a party: records with the same people are a **possible match** (same people, not
  the same record), else **nothing found**, naming the people searched.

For a statement with people and a period, each phone's records with those people in the period are listed (a
possible match: they are the same people, not the statement itself). For a statement with a place (latitude and
longitude), each phone's own positions in the period are compared: a position within the distance **agrees**, a
phone whose every position in the period is farther **disagrees**, a cell tower nearby is a possible match ("near,
not at"). A photo's place is where a photo was taken, never where the phone was: it is listed as a possible match
with those words and never agrees or disagrees.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from services.elsewhere import words as W
from services.phone import time_display as T

COPY_SECONDS = 120
EITHER_SIDE_DAYS = 2   # 'recording at the time': the conversation on both sides within two days
PHOTO_KINDS = ("media_place",)
TOWER_KINDS = ("other:CellTower",)
NOT_POSITIONS = PHOTO_KINDS + ("other:SearchedItem", "other:InstantMessage")
KIND_WORDS = {"message": "message", "chat_activity": "message", "call": "call", "voicemail": "voicemail",
              "email": "email"}


def _deleted(state):
    return (state or "").lower() in ("deleted", "trash")


def _when(instant, zone):
    if instant is None:
        return "no time recorded"
    lt = T.local(instant, zone)
    return "%s, %s" % (W.day_text(lt.date()), T.format_row(instant, zone))


def _cite(uid, phone, what, instant, zone):
    return {"kind": "phone_record", "id": uid, "href": "rec://%s" % uid, "phone": phone,
            "label": "%s · %s %s" % (phone, what, _when(instant, zone))}


def _owners(conn, case_id):
    """``{extraction_id: (number key, name)}`` from the report's own owner details (best tier first)."""
    out = {}
    for r in conn.execute(text(
            "SELECT extraction_id::text AS ext, candidate_kind, identity_key, name, tier, occurrences FROM "
            "pv_owner_candidate WHERE case_id = CAST(:c AS uuid) AND candidate_kind IN ('number', 'name') "
            "ORDER BY extraction_id, tier NULLS LAST, occurrences DESC"), {"c": str(case_id)}):
        key, name = out.get(r.ext, (None, None))
        if r.candidate_kind == "number" and key is None:
            key = W.number_key((r.identity_key or "").split(":", 1)[-1])
        if r.candidate_kind == "name" and name is None:
            name = r.name
        out[r.ext] = (key, name)
    return out


def _phones(conn, case_id):
    from services.phone import readings
    labels = readings.phone_labels(conn, str(case_id))
    rows = conn.execute(text(
        "SELECT id::text AS ext FROM phone_extractions WHERE case_id = CAST(:c AS uuid) AND standing = 'active' "
        "ORDER BY created_at, id"), {"c": str(case_id)}).fetchall()
    return [(r.ext, labels.get(r.ext, "Phone")) for r in rows]


def _party_keys(conn, event_uids):
    out = {}
    if not event_uids:
        return out
    for r in conn.execute(text(
            "SELECT event_uid::text AS ev, identifier_raw, name_in_record FROM pv_comm_party WHERE event_uid = "
            "ANY(CAST(:u AS uuid[]))"), {"u": list(event_uids)}):
        k = W.number_key(r.identifier_raw) if r.identifier_raw and "@" not in r.identifier_raw else None
        out.setdefault(r.ev, set())
        if k:
            out[r.ev].add(k)
        elif r.identifier_raw:
            out[r.ev].add(r.identifier_raw.lower())
    return out


def _record_keys(rec):
    keys = set()
    for p in rec.people:
        keys.update(p.numbers)
        keys.update(p.emails)
    return keys


def _events_with(conn, ext, keys, start=None, end=None, limit=None):
    """Events on phone ``ext`` with any of ``keys`` (number keys or e-mail addresses), oldest first."""
    if not keys:
        return []
    nums = [k for k in keys if "@" not in k]
    mails = [k for k in keys if "@" in k]
    sql = ("SELECT DISTINCT c.event_uid::text AS ev, c.record_uid::text AS uid, c.kind, c.sort_instant, "
           "c.deleted_state FROM pv_comm_event c JOIN pv_comm_party p ON p.event_uid = c.event_uid WHERE "
           "c.extraction_id = CAST(:e AS uuid) AND (right(regexp_replace(coalesce(p.identifier_raw, ''), '\\D', '', "
           "'g'), 10) = ANY(:n) OR lower(p.identifier_raw) = ANY(:m))")
    params = {"e": ext, "n": nums or [""], "m": mails or [""]}
    if start is not None:
        sql += " AND c.sort_instant >= :s"
        params["s"] = start
    if end is not None:
        sql += " AND c.sort_instant < :t"
        params["t"] = end
    sql += " ORDER BY c.sort_instant NULLS LAST"
    if limit:
        sql += " LIMIT %d" % int(limit)
    return conn.execute(text(sql), params).fetchall()


def _copy_on(conn, rec, ext):
    if rec.instant is None or rec.kind is None:
        return None
    rows = conn.execute(text(
        "SELECT event_uid::text AS ev, record_uid::text AS uid, body, subject, sort_instant, deleted_state FROM "
        "pv_comm_event WHERE extraction_id = CAST(:e AS uuid) AND kind = :k AND sort_instant BETWEEN :a AND :b"),
        {"e": ext, "k": rec.kind, "a": rec.instant - timedelta(seconds=COPY_SECONDS),
         "b": rec.instant + timedelta(seconds=COPY_SECONDS)}).fetchall()
    mine = W.fold(rec.body)
    keys = _record_keys(rec)
    parties = _party_keys(conn, [r.ev for r in rows]) if rows else {}
    best = None
    for r in rows:
        theirs = W.fold(" ".join(x for x in (r.subject, r.body) if x))
        if mine and theirs:
            same = mine == theirs
        else:
            same = not mine and not theirs and len(keys & parties.get(r.ev, set())) >= 2
        if same:
            gap = abs((r.sort_instant - rec.instant).total_seconds())
            if best is None or gap < best[0]:
                best = (gap, r)
    return best[1] if best else None


def _names(rec, keys):
    out = []
    for p in rec.people:
        if set(p.numbers) & keys or set(p.emails) & keys:
            out.append(p.shown or p.label())
    return W.join_words(out) or "these people"


def record_items(conn, case_id, rec, phones, owners, zone, prefix=""):
    items = []
    here = dict(phones).get(rec.extraction_id, "this phone")
    what = KIND_WORDS.get(rec.kind or "", "record")
    keys = _record_keys(rec)
    here_owner = owners.get(rec.extraction_id, (None, None))[0] or rec.owner_key
    for ext, label in phones:
        if ext == rec.extraction_id:
            continue
        owner_key, owner_name = owners.get(ext, (None, None))
        copy = _copy_on(conn, rec, ext)
        if copy is not None:
            gap = abs((copy.sort_instant - rec.instant).total_seconds())
            words = "%sAlso on %s: the same %s, %s." % (prefix, label, what,
                                                       "same minute" if gap < 60 else "%d seconds apart" % gap)
            if _deleted(copy.deleted_state) and not _deleted(rec.deleted_state):
                words += " It is deleted on %s and intact on %s." % (label, here)
            elif _deleted(rec.deleted_state) and not _deleted(copy.deleted_state):
                words += " It is deleted on %s and intact on %s." % (here, label)
            items.append(W.item(W.AGREES, words, "Same kind of record, same text and the same time, within %d "
                                "seconds, on another phone." % COPY_SECONDS,
                                _cite(copy.uid, label, what, copy.sort_instant, zone), ["time", "text"]))
            continue
        party = owner_key is not None and owner_key in keys
        # on a party's phone the other side of the conversation includes this phone's own owner
        others = keys - {owner_key} if party else keys - {here_owner, owner_key}
        if party:
            who = owner_name or "its owner"
            if rec.instant is None or not others:
                items.append(W.item(W.NOTHING, "%s%s belongs to %s, a party to this %s, and does not hold it." % (
                    prefix, label, who, what), "No copy on %s; this %s has no time or no other party, so the "
                    "conversation around it could not be checked." % (label, what), None, ["number"]))
                continue
            lo, hi = rec.instant - timedelta(days=EITHER_SIDE_DAYS), rec.instant + timedelta(days=EITHER_SIDE_DAYS)
            around = _events_with(conn, ext, others, lo, hi)
            before = [e for e in around if e.sort_instant and e.sort_instant < rec.instant]
            after = [e for e in around if e.sort_instant and e.sort_instant > rec.instant]
            if before and after:
                b, a = before[-1], after[0]
                items.append(W.item(
                    W.MISSING, "%s%s belongs to %s, a party to this %s. It holds the conversation either side of it "
                    "(%s and %s) but not this %s." % (prefix, label, who, what, _when(b.sort_instant, zone),
                                                      _when(a.sort_instant, zone), what),
                    "The owner's number on %s is a party to this %s, and %s holds records with %s before and after "
                    "it, within %d days." % (label, what, label, _names(rec, others), EITHER_SIDE_DAYS),
                    _cite(b.uid, label, KIND_WORDS.get(b.kind, "record"), b.sort_instant, zone), ["number", "time"],
                    also=[_cite(a.uid, label, KIND_WORDS.get(a.kind, "record"), a.sort_instant, zone)]))
            else:
                side = "after it" if before else ("before it" if after else "within %d days of it" % EITHER_SIDE_DAYS)
                items.append(W.item(
                    W.NOTHING, "%s%s belongs to %s, a party to this %s, and does not hold it. It holds no record with "
                    "%s %s." % (prefix, label, who, what, _names(rec, others), side),
                    "A phone can only show what it held when it was examined; with no records on that side, its "
                    "silence says nothing either way.", None, ["number"]))
            continue
        shared = _events_with(conn, ext, others, limit=500) if others else []
        if shared:
            nearest = min(shared, key=lambda e: abs((e.sort_instant - rec.instant).total_seconds())
                          if (e.sort_instant and rec.instant) else 1e18)
            gap = ("" if not (nearest.sort_instant and rec.instant) else
                   "; the nearest is %s" % W.when_words(W.days_apart(rec.instant, nearest.sort_instant)))
            items.append(W.item(
                W.POSSIBLE, "%sNot on %s, which holds %s with %s%s." % (
                    prefix, label, W.plural(len(shared), "record") if len(shared) < 500 else "500 or more records",
                    _names(rec, others), gap),
                "Same people, not the same record.",
                _cite(nearest.uid, label, KIND_WORDS.get(nearest.kind, "record"), nearest.sort_instant, zone),
                ["number"]))
        else:
            items.append(W.item(
                W.NOTHING, "%sNot on %s. It holds no record with %s." % (prefix, label, _names(rec, others)),
                "Searched every message, call and email on %s for the numbers and addresses of the people in this "
                "%s." % (label, what), None, ["number"]))
    return items


def _people_items(conn, subject, phones, owners, zone):
    from services.elsewhere.subject import window
    keys = set(subject.number_keys()) | {e for p in subject.people for e in p.emails}
    if not keys:
        return []
    lo, hi = window(subject, 0, 0)
    start = datetime(lo.year, lo.month, lo.day, tzinfo=timezone.utc) if lo else None
    end = datetime(hi.year, hi.month, hi.day, tzinfo=timezone.utc) + timedelta(days=1) if hi else None
    names = W.join_words([p.label() for p in subject.people if p.numbers or p.emails])
    items = []
    for ext, label in phones:
        owner_key = owners.get(ext, (None, None))[0]
        want = keys - {owner_key}
        if not want:
            continue
        rows = _events_with(conn, ext, want, start, end, limit=1000)
        if rows:
            items.append(W.item(
                W.POSSIBLE, "%s holds %s with %s %s." % (label, W.plural(len(rows), "record") if len(rows) < 1000
                                                         else "1,000 or more records", names, W.span_text(lo, hi)),
                "Same people in the same period; what they say is not compared here.",
                _cite(rows[0].uid, label, KIND_WORDS.get(rows[0].kind, "record"), rows[0].sort_instant, zone),
                ["number", "date"]))
        else:
            items.append(W.item(W.NOTHING, "%s holds no record with %s %s." % (label, names, W.span_text(lo, hi)),
                                "Searched every message, call and email on %s for their numbers and addresses." %
                                label, None, ["number"]))
    return items


def _km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def _dist_words(km):
    return "%d m" % round(km * 1000) if km < 1 else ("%.1f km" % km if km < 10 else "%d km" % round(km))


def place_items(conn, case_id, subject, phones, owners, zone):
    from services.elsewhere.subject import window
    items = []
    lo, hi = window(subject, 0, 0)
    if lo is None:
        return items
    start = datetime(lo.year, lo.month, lo.day, tzinfo=timezone.utc)
    end = datetime(hi.year, hi.month, hi.day, tzinfo=timezone.utc) + timedelta(days=1)
    keys = set(subject.number_keys())
    wanted = [(e, l) for e, l in phones if not keys or owners.get(e, (None, None))[0] in keys] or phones
    for place in subject.places:
        if place.get("lat") is None or place.get("lon") is None:
            continue
        name = place.get("name") or "the place given"
        radius_km = float(place.get("radius_m") or 500) / 1000.0
        for ext, label in wanted:
            rows = conn.execute(text(
                "SELECT record_uid::text AS uid, lat, lon, accuracy_m, source_kind, instant FROM pv_location_point "
                "WHERE extraction_id = CAST(:e AS uuid) AND instant >= :s AND instant < :t"),
                {"e": ext, "s": start, "t": end}).fetchall()
            pos, towers, photos = [], [], []
            for r in rows:
                km = _km(place["lat"], place["lon"], r.lat, r.lon)
                slack = float(r.accuracy_m or 0) / 1000.0
                entry = (km, slack, r)
                if r.source_kind in PHOTO_KINDS:
                    photos.append(entry)
                elif r.source_kind in TOWER_KINDS:
                    towers.append(entry)
                elif r.source_kind not in NOT_POSITIONS:
                    pos.append(entry)
            span = W.span_text(lo, hi)
            near = [e for e in pos if e[0] - e[1] <= radius_km]
            if near:
                km, _, r = min(near, key=lambda e: e[0])
                items.append(W.item(W.AGREES, "%s was within %s of %s %s (%s)." % (
                    label, _dist_words(max(km, 0.001)), name, span, _when(r.instant, zone)),
                    "A position the phone recorded itself, within %s of the place." % _dist_words(radius_km),
                    _cite(r.uid, label, "position", r.instant, zone), ["place", "time"]))
            elif pos:
                km, _, r = min(pos, key=lambda e: e[0])
                items.append(W.item(W.DISAGREES, "%s recorded %s %s; the nearest is %s from %s." % (
                    label, W.plural(len(pos), "position"), span, _dist_words(km), name),
                    "Every position the phone recorded in the period is farther than %s from the place, even "
                    "allowing for each position's stated accuracy." % _dist_words(radius_km),
                    _cite(r.uid, label, "position", r.instant, zone), ["place", "time"]))
            if not near:
                close_towers = [e for e in towers if e[0] - e[1] <= max(radius_km, 2.0)]
                if close_towers:
                    km, _, r = min(close_towers, key=lambda e: e[0])
                    items.append(W.item(W.POSSIBLE, "%s used a cell tower %s from %s %s." % (
                        label, _dist_words(km), name, span), "A cell tower puts a phone near a place, not at it.",
                        _cite(r.uid, label, "cell tower", r.instant, zone), ["place", "time"]))
            near_photos = [e for e in photos if e[0] - e[1] <= radius_km]
            if near_photos:
                km, _, r = min(near_photos, key=lambda e: e[0])
                items.append(W.item(W.POSSIBLE, "A photo on %s has a place %s from %s in its data, %s." % (
                    label, _dist_words(km), name, span),
                    "A photo's place is where the photo was taken, not where the phone was.",
                    _cite(r.uid, label, "photo", r.instant, zone), ["place"], photo_place=True))
            if not pos and not towers and not near_photos:
                items.append(W.item(W.NOTHING, "%s recorded no position %s." % (label, span),
                                    "Searched the phone's own positions and cell towers; photo places are not "
                                    "counted as where the phone was.", None, ["place"]))
    return items


def part(conn, case_id, subject, zone) -> dict:
    phones = _phones(conn, case_id)
    owners = _owners(conn, case_id)
    items = []
    many = len(subject.records) > 1
    for rec in subject.records:
        prefix = ("%s %s: " % (dict(phones).get(rec.extraction_id, "Phone"), _when(rec.instant, zone))) if many else ""
        items.extend(record_items(conn, case_id, rec, phones, owners, zone, prefix))
    if subject.kind == "statement" and (subject.start or subject.end) and not subject.records:
        items.extend(_people_items(conn, subject, phones, owners, zone))
    items.extend(place_items(conn, case_id, subject, phones, owners, zone))
    searched = "%s in this case: %s." % (W.plural(len(phones), "phone"), W.join_words([l for _, l in phones]))
    if len(phones) <= 1 and not subject.places:
        items.append(W.item(W.NOTHING, "This case has no other phone to compare.", "Only one phone is in the case.",
                            None))
    elif not items:
        items.append(W.item(W.NOTHING, "Nothing on the phones to compare: no record, people with numbers, or place "
                            "with a position was given.", "The phones are searched by record, number and place.",
                            None))
    return {"searched": searched, "items": items}
