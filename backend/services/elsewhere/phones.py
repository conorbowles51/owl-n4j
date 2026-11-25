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


def _copies(conn, case_id, rec):
    """``{extraction_id: row}``: the nearest copy of ``rec`` on each other phone, in one query."""
    if rec.instant is None or rec.kind is None:
        return {}
    rows = conn.execute(text(
        "SELECT extraction_id::text AS ext, event_uid::text AS ev, record_uid::text AS uid, body, subject, "
        "sort_instant, deleted_state FROM pv_comm_event WHERE case_id = CAST(:c AS uuid) AND extraction_id <> "
        "CAST(:here AS uuid) AND kind = :k AND sort_instant BETWEEN :a AND :b"),
        {"c": str(case_id), "here": rec.extraction_id, "k": rec.kind,
         "a": rec.instant - timedelta(seconds=COPY_SECONDS), "b": rec.instant + timedelta(seconds=COPY_SECONDS)}
    ).fetchall()
    mine = W.fold(rec.body)
    keys = _record_keys(rec)
    parties = _party_keys(conn, [r.ev for r in rows]) if rows and not mine else {}
    best = {}
    for r in rows:
        theirs = W.fold(" ".join(x for x in (r.subject, r.body) if x))
        if mine and theirs:
            same = mine == theirs
        else:
            same = not mine and not theirs and len(keys & parties.get(r.ev, set())) >= 2
        if same:
            gap = abs((r.sort_instant - rec.instant).total_seconds())
            if r.ext not in best or gap < best[r.ext][0]:
                best[r.ext] = (gap, r)
    return {e: v[1] for e, v in best.items()}


STATS_SQL = (
    "WITH w AS (SELECT * FROM unnest(CAST(:exts AS uuid[]), CAST(:ks AS text[])) AS w(ext, k)), "
    "ev AS (SELECT DISTINCT c.extraction_id, c.event_uid, c.record_uid, c.kind, c.sort_instant FROM pv_comm_event c "
    "JOIN pv_comm_party p ON p.event_uid = c.event_uid JOIN w ON w.ext = c.extraction_id AND (w.k = "
    "right(regexp_replace(coalesce(p.identifier_raw, ''), '\\D', '', 'g'), 10) OR w.k = lower(p.identifier_raw)) "
    "WHERE c.case_id = CAST(:c AS uuid) AND c.sort_instant IS NOT NULL{window}) "
    "SELECT extraction_id::text AS ext, count(*) AS n, "
    "(array_agg(record_uid::text ORDER BY sort_instant DESC) FILTER (WHERE sort_instant < :t))[1] AS b_uid, "
    "(array_agg(kind ORDER BY sort_instant DESC) FILTER (WHERE sort_instant < :t))[1] AS b_kind, "
    "max(sort_instant) FILTER (WHERE sort_instant < :t) AS b_at, "
    "(array_agg(record_uid::text ORDER BY sort_instant) FILTER (WHERE sort_instant > :t))[1] AS a_uid, "
    "(array_agg(kind ORDER BY sort_instant) FILTER (WHERE sort_instant > :t))[1] AS a_kind, "
    "min(sort_instant) FILTER (WHERE sort_instant > :t) AS a_at, "
    "(array_agg(record_uid::text ORDER BY sort_instant))[1] AS f_uid, "
    "(array_agg(kind ORDER BY sort_instant))[1] AS f_kind, min(sort_instant) AS f_at "
    "FROM ev GROUP BY 1")


def _stats(conn, case_id, wants, t=None, start=None, end=None):
    """``{extraction_id: row}`` for the records on each phone with any of that phone's keys (``wants``: ``{ext:
    keys}``), in one query: how many, the nearest before and after ``t``, and the first."""
    exts, ks = [], []
    for ext, keys in wants.items():
        for k in keys:
            exts.append(ext)
            ks.append(k)
    if not exts:
        return {}
    window = ""
    params = {"c": str(case_id), "exts": exts, "ks": ks,
              "t": t or datetime(9999, 1, 1, tzinfo=timezone.utc)}
    if start is not None:
        window += " AND c.sort_instant >= :s"
        params["s"] = start
    if end is not None:
        window += " AND c.sort_instant < :e"
        params["e"] = end
    return {r.ext: r for r in conn.execute(text(STATS_SQL.format(window=window)), params).fetchall()}


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
    copies = _copies(conn, case_id, rec)
    party_wants, other_wants = {}, {}
    for ext, _ in phones:
        if ext == rec.extraction_id or ext in copies:
            continue
        owner_key = owners.get(ext, (None, None))[0]
        if owner_key is not None and owner_key in keys:
            # on a party's phone the other side of the conversation includes this phone's own owner
            party_wants[ext] = keys - {owner_key}
        else:
            other_wants[ext] = keys - {here_owner, owner_key}
    around = {}
    if rec.instant is not None and party_wants:
        around = _stats(conn, case_id, party_wants, rec.instant, rec.instant - timedelta(days=EITHER_SIDE_DAYS),
                        rec.instant + timedelta(days=EITHER_SIDE_DAYS))
    shared = _stats(conn, case_id, other_wants, rec.instant)
    for ext, label in phones:
        if ext == rec.extraction_id:
            continue
        owner_key, owner_name = owners.get(ext, (None, None))
        copy = copies.get(ext)
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
        if ext in party_wants:
            others = party_wants[ext]
            who = owner_name or "its owner"
            if rec.instant is None or not others:
                items.append(W.item(W.NOTHING, "%s%s belongs to %s, a party to this %s, and does not hold it." % (
                    prefix, label, who, what), "No copy on %s; this %s has no time or no other party, so the "
                    "conversation around it could not be checked." % (label, what), None, ["number"]))
                continue
            st = around.get(ext)
            if st is not None and st.b_uid and st.a_uid:
                items.append(W.item(
                    W.MISSING, "%s%s belongs to %s, a party to this %s. It holds the conversation either side of it "
                    "(%s and %s) but not this %s." % (prefix, label, who, what, _when(st.b_at, zone),
                                                      _when(st.a_at, zone), what),
                    "The owner's number on %s is a party to this %s, and %s holds records with %s before and after "
                    "it, within %d days." % (label, what, label, _names(rec, others), EITHER_SIDE_DAYS),
                    _cite(st.b_uid, label, KIND_WORDS.get(st.b_kind, "record"), st.b_at, zone), ["number", "time"],
                    also=[_cite(st.a_uid, label, KIND_WORDS.get(st.a_kind, "record"), st.a_at, zone)]))
            else:
                side = ("after it" if st is not None and st.b_uid else
                        "before it" if st is not None and st.a_uid else "within %d days of it" % EITHER_SIDE_DAYS)
                items.append(W.item(
                    W.NOTHING, "%s%s belongs to %s, a party to this %s, and does not hold it. It holds no record with "
                    "%s %s." % (prefix, label, who, what, _names(rec, others), side),
                    "A phone can only show what it held when it was examined; with no records on that side, its "
                    "silence says nothing either way.", None, ["number"]))
            continue
        others = other_wants.get(ext, set())
        st = shared.get(ext)
        if st is not None and st.n:
            cands = [(uid, kind, at) for uid, kind, at in ((st.b_uid, st.b_kind, st.b_at), (st.a_uid, st.a_kind, st.a_at))
                     if uid]
            if rec.instant is not None and cands:
                uid, kind, at = min(cands, key=lambda c: abs((c[2] - rec.instant).total_seconds()))
                gap = "; the nearest is %s" % W.when_words(W.days_apart(rec.instant, at))
            else:
                uid, kind, at, gap = st.f_uid, st.f_kind, st.f_at, ""
            items.append(W.item(
                W.POSSIBLE, "%sNot on %s, which holds %s with %s%s." % (
                    prefix, label, W.plural(int(st.n), "record"), _names(rec, others), gap),
                "Same people, not the same record.",
                _cite(uid, label, KIND_WORDS.get(kind, "record"), at, zone), ["number"]))
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
    wants = {}
    for ext, _ in phones:
        want = keys - {owners.get(ext, (None, None))[0]}
        if want:
            wants[ext] = want
    stats = _stats(conn, subject.case_id, wants, None, start, end)
    items = []
    for ext, label in phones:
        if ext not in wants:
            continue
        st = stats.get(ext)
        if st is not None and st.n:
            items.append(W.item(
                W.POSSIBLE, "%s holds %s with %s %s." % (label, W.plural(int(st.n), "record"), names,
                                                         W.span_text(lo, hi)),
                "Same people in the same period; what they say is not compared here.",
                _cite(st.f_uid, label, KIND_WORDS.get(st.f_kind, "record"), st.f_at, zone), ["number", "date"]))
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
