"""Approach 10: plans and self-reported places (docs/cellebrite/05 section 13; unit 05-S12b, cb-gated-spread).

What the phone's calendar, social check-ins and notes say a person planned or reported doing, where those carry a
place, and how they compare with the phone's own location at the same time.

Built on every case with no count gate (Neil 2026-11-04, "We don't want to miss things based on an arbitrary
cutoff"): the old build gate (20 placed items in a case) is gone. Every calendar entry, check-in and note is listed;
a placed item is compared; an unplaced one is listed as such, with the true counts on screen.

Method (13.3):

1. Repeating calendar entries are expanded (``occurrences``: RFC 5545 semantics for the stored fields
   ``RepeatRule`` Daily / Weekly / Monthly / Yearly, ``RepeatInterval``, ``RepeatDay`` weekday names for a weekly
   rule, ``RepeatUntil``). Occurrences run to ``RepeatUntil`` or, without it, to the last instant the phone records
   (its extraction), never further. A day of the month or year that a period lacks (31 April, 29 February) is
   skipped, as RFC 5545 does.
2. Places: an item is placed only by coordinates the phone itself holds for that record (04's place observations of
   kind ``planned`` for a calendar entry and ``declared`` for a check-in). A place written as text (calendar
   ``Location``) is shown as written and not geocoded: no offline forward geocoder or case place list is installed
   (standing decision 8). Reverse if a case place list or an in-house forward geocoder is added.
3. Each dated, placed item (each occurrence) is compared with 04's presence observations of the same phone that
   overlap its window (the calendar entry from start to end, one hour when the end is not recorded; a check-in one
   hour either side of its time). Per observation: distance against the sum of the two uncertainty radii (04's
   radius; ``ASSUMED_RADIUS_M`` where a side states none). ``consistent``: every observation within the radii;
   ``inconsistent``: every observation outside them (non-overlapping uncertainty); ``mixed``: some of each;
   ``no_data``: the phone holds no location in the window.
4. Notes: amounts read by approach 1's parser (``money_parse.parse``: a p4 reading, never a ledger row) and case
   names and numbers by approach 7's vocabulary.

Strength (one scale with approach 1's matches: strong, moderate, weak, faint; reasons in two parts, ``match`` and
``substantiation``; a rule computes it, never a model). These levels are rules of thumb: no measurement on a case
set them.

- ``strong``: consistent or inconsistent, and the item and at least one observation each state their own radius.
- ``moderate``: consistent or inconsistent, with a radius assumed on one side.
- ``weak``: mixed (observations in the window disagree).
- ``faint``: not compared (no location in the window, a place as text only, or no place); listed so it is not
  missed.

Every list states its total.
"""
from __future__ import annotations

import calendar as _cal
import re
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import text

from services.phone_analysis import fields as FV

CODE = "plans"
VERSION = "10.2"
PARAMETERS = {
    "checkin_window_minutes": {"default": 60, "min": 5, "max": 1440},
    "assumed_radius_m": {"default": 1000, "min": 50, "max": 50000},
}
KINDS = ("consistent", "inconsistent", "mixed", "no_data", "place_as_text", "no_place", "note")
LEVELS = ("strong", "moderate", "weak", "faint")
SUPPORTS = ("placed_by_phone", "fixes_in_window", "within_radii", "amount_read", "case_terms", "occurrence")
UNDERCUTS = ("plan_not_attendance", "shared_calendar", "checkin_elsewhere", "place_text_ambiguous",
             "radius_assumed", "no_location_in_window", "synced_attribution", "offset_absent")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
DEFAULT_END = timedelta(hours=1)
RULE_OF_THUMB = ("The strength levels are rules of thumb: both sides stating a radius is strong, one radius assumed "
                 "moderate, disagreeing locations weak, not compared faint; no measurement on this case set them.")
SIGNALS = [
    {"code": "calendar", "label": "Calendar entries"},
    {"code": "checkins", "label": "Social check-ins"},
    {"code": "notes", "label": "Notes"},
    {"code": "location", "label": "Location records"},
]
UNDERCUT_WORDS = {
    "plan_not_attendance": "A calendar entry is a plan, not a record that anyone attended.",
    "shared_calendar": "The entry may come from a shared or subscribed calendar (its account is shown).",
    "checkin_elsewhere": "A check-in can be made from somewhere else.",
    "place_text_ambiguous": "A place written as text can name more than one place; it is not placed here.",
    "radius_assumed": "One side states no accuracy; a radius of {r:,} m is assumed for it.",
    "no_location_in_window": "The phone holds no location record in this window, so nothing is compared.",
    "synced_attribution": "A location used is attributed to a synced account, not this device.",
    "offset_absent": "A time used was written without a time zone.",
}
WEEKDAYS = {name: i for i, name in enumerate(("monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
                                              "sunday"))}
_last = {"counts": {}}


def _d(code, detail, locators=()):
    return {"code": code, "detail": detail, "locators": [str(x) for x in locators]}


def _add_months(t, n):
    y, m = divmod(t.month - 1 + n, 12)
    y, m = t.year + y, m + 1
    if t.day > _cal.monthrange(y, m)[1]:
        return None
    return t.replace(year=y, month=m)


def occurrences(start, rule=None, interval=None, until=None, repeat_day=None, horizon=None) -> list:
    """Start instants of every occurrence (13.3 step 1). ``until`` (``RepeatUntil``) or else ``horizon`` (the
    phone's last instant) bounds a repeating rule; a rule with neither yields the first occurrence only."""
    rule = (rule or "").strip().lower()
    step = max(1, int(interval or 1))
    if rule not in ("daily", "weekly", "monthly", "yearly"):
        return [start]
    end = until or horizon
    if end is None:
        return [start]
    out = []
    if rule == "daily":
        t = start
        while t <= end:
            out.append(t)
            t += timedelta(days=step)
    elif rule == "weekly":
        days = sorted({WEEKDAYS[w] for w in re.findall(r"[a-z]+", (repeat_day or "").lower()) if w in WEEKDAYS}
                      or {start.weekday()})
        week = start - timedelta(days=start.weekday())
        while week <= end:
            for wd in days:
                t = week + timedelta(days=wd)
                if start <= t <= end:
                    out.append(t)
            week += timedelta(weeks=step)
    else:
        months = 1 if rule == "monthly" else 12
        k = 0
        while True:
            t = _add_months(start, k * months * step) if k else start
            probe = start.replace(day=1)
            first = _add_months(probe, k * months * step) if k else probe
            if first is None or first > end:
                break
            if t is not None and t <= end:
                out.append(t)
            k += 1
    # RFC 5545: the start itself is always the first occurrence, even when the rule's days or bound leave it out
    if not out or out[0] != start:
        out.insert(0, start)
    return out


def compare(item, fixes, assumed_radius_m) -> dict:
    """13.3 step 3 for one placed occurrence. ``item``: lat, lon, radius_m (None = not stated); ``fixes``: dicts
    with lat, lon, radius_m. Returns kind, strength, counts, nearest distance."""
    from services.pattern_of_life.places import haversine_m
    if not fixes:
        return {"kind": "no_data", "strength": "faint", "within": 0, "outside": 0, "fixes": 0, "assumed": False,
                "nearest_m": None, "margin_m": None}
    within = outside = 0
    stated_fix = any(f.get("radius_m") is not None for f in fixes)
    nearest, margin = None, None
    for f in fixes:
        ri = item["radius_m"] if item.get("radius_m") is not None else assumed_radius_m
        rf = f["radius_m"] if f.get("radius_m") is not None else assumed_radius_m
        d = haversine_m(item["lat"], item["lon"], f["lat"], f["lon"])
        if d <= ri + rf:
            within += 1
        else:
            outside += 1
        if nearest is None or d < nearest:
            nearest, margin = d, d - (ri + rf)
    one_side_assumed = item.get("radius_m") is None or not stated_fix
    if within and outside:
        kind, level = "mixed", "weak"
    else:
        kind = "consistent" if within else "inconsistent"
        level = "moderate" if one_side_assumed else "strong"
    return {"kind": kind, "strength": level, "within": within, "outside": outside, "fixes": len(fixes),
            "assumed": one_side_assumed, "nearest_m": round(nearest, 1), "margin_m": round(margin, 1)}


def coverage(conn, case_id) -> dict:
    phones = {}
    for ext, label in FV.active_phones(conn, case_id).items():
        n = FV.type_counts(conn, ext, ("CalendarEntry", "SocialMediaActivity", "Note"))
        loc = int(conn.execute(text("SELECT count(*) FROM pol_place_observation WHERE extraction_id = :e AND kind = "
                                    "'presence'"), {"e": ext}).scalar() or 0)
        phones[ext] = {"label": label, "signals": {
            "calendar": {"carries_signal": n.get("CalendarEntry", 0) > 0, "records": n.get("CalendarEntry", 0)},
            "checkins": {"carries_signal": n.get("SocialMediaActivity", 0) > 0,
                         "records": n.get("SocialMediaActivity", 0)},
            "notes": {"carries_signal": n.get("Note", 0) > 0, "records": n.get("Note", 0)},
            "location": {"carries_signal": loc > 0, "records": loc}}}
    return {"phones": phones, "signals": SIGNALS}


def _placed(conn, ext, kinds) -> dict:
    """``{record_uid: {lat, lon, radius_m}}`` from 04's observations of the given kinds (the record's own
    coordinates)."""
    out = {}
    for r in conn.execute(text(
            "SELECT record_uid::text AS u, lat, lon, radius_m FROM pol_place_observation WHERE extraction_id = :e AND "
            "kind = ANY(:k) AND lat IS NOT NULL AND lon IS NOT NULL ORDER BY id"), {"e": ext, "k": list(kinds)}):
        out.setdefault(r.u, {"lat": float(r.lat), "lon": float(r.lon),
                             "radius_m": float(r.radius_m) if r.radius_m is not None else None})
    return out


def _fixes(conn, ext, a, b) -> list:
    return [{"lat": float(r.lat), "lon": float(r.lon), "radius_m": float(r.radius_m) if r.radius_m is not None
             else None, "synced": "synced_from_account" in (r.attribution_flags or []),
             "offset_absent": r.offset_status != "explicit", "record_uid": str(r.record_uid) if r.record_uid else None}
            for r in conn.execute(text(
                "SELECT lat, lon, radius_m, attribution_flags, offset_status, record_uid FROM pol_place_observation "
                "WHERE extraction_id = :e AND kind = 'presence' AND lat IS NOT NULL AND lon IS NOT NULL AND start_utc "
                "<= :b AND end_utc >= :a ORDER BY start_utc, id"), {"e": ext, "a": a, "b": b})]


def _horizon(conn, ext):
    return conn.execute(text("SELECT max(instant) FROM pv_time WHERE extraction_id = :e AND instant IS NOT NULL"),
                        {"e": ext}).scalar()


def _all(conn, ext, model_type, found) -> dict:
    """Every record of the type, including those carrying none of the fields read (nothing is left out)."""
    out = dict(found)
    for (u,) in conn.execute(text("SELECT record_uid::text FROM pv_record WHERE extraction_id = :e AND model_type = :t"),
                             {"e": ext, "t": model_type}):
        out.setdefault(u, {"model_type": model_type, "deleted_state": None, "parent_uid": None, "values": {}})
    return out


def _first(v, name):
    vals = v["values"].get(name) or []
    return vals[0] if vals else None


def _iso(t):
    return t.isoformat() if t is not None else None


def _item_result(ext, label, uid, source, when, end, place, cmp_, text_place, params, extra):
    """One result for one dated item (or occurrence)."""
    assumed_r = params["assumed_radius_m"]
    under = [_d("plan_not_attendance", UNDERCUT_WORDS["plan_not_attendance"])] if source == "calendar" else \
        [_d("checkin_elsewhere", UNDERCUT_WORDS["checkin_elsewhere"])]
    if source == "calendar" and extra.get("account"):
        under.append(_d("shared_calendar", UNDERCUT_WORDS["shared_calendar"]))
    supports = []
    if cmp_ is not None:
        kind, level = cmp_["kind"], cmp_["strength"]
        if kind == "no_data":
            under.append(_d("no_location_in_window", UNDERCUT_WORDS["no_location_in_window"]))
            match = ["Placed by the phone's own coordinates for this record; not compared: no location in the window."]
        else:
            supports.append(_d("placed_by_phone", "Placed by the phone's own coordinates for this record."))
            supports.append(_d("fixes_in_window", "%d location records in the window: %d within the radii, %d "
                                                  "outside." % (cmp_["fixes"], cmp_["within"], cmp_["outside"])))
            match = ["%s: %d of %d location records in the window are within the two radii; the nearest is %s m "
                     "away (%s m %s the radii)." % (kind.capitalize(), cmp_["within"], cmp_["fixes"],
                                                    "{:,}".format(int(cmp_["nearest_m"])),
                                                    "{:,}".format(abs(int(cmp_["margin_m"]))),
                                                    "beyond" if cmp_["margin_m"] > 0 else "inside")]
            if cmp_["assumed"]:
                under.append(_d("radius_assumed", UNDERCUT_WORDS["radius_assumed"].format(r=assumed_r)))
        subst = ["%d location records of this phone overlap the window." % cmp_["fixes"]]
        if cmp_.get("synced"):
            under.append(_d("synced_attribution", UNDERCUT_WORDS["synced_attribution"]))
    elif text_place:
        kind, level = "place_as_text", "faint"
        match = ["The place is written as text and is not placed, so nothing is compared."]
        subst = ["Not compared."]
        under.append(_d("place_text_ambiguous", UNDERCUT_WORDS["place_text_ambiguous"]))
    else:
        kind, level = "no_place", "faint"
        match = ["No place is recorded, so nothing is compared."]
        subst = ["Not compared."]
    measures = {"phone_label": label, "source": source, "start": _iso(when), "end": _iso(end),
                "place_text": text_place, "placed": place is not None,
                "comparison": cmp_, "reasons": {"match": match, "substantiation": subst},
                "rule_of_thumb": RULE_OF_THUMB}
    measures.update(extra)
    fp = "occurrence:%s" % when.isoformat() if extra.get("occurrence_count", 1) > 1 and when is not None else None
    return {"kind": kind, "strength": level, "measures": measures,
            "directions": {"supports": supports, "undercuts": under},
            "period_start": when, "period_end": end or when,
            "records": [{"extraction_id": ext, "record_uid": uid, "field_path": fp, "role": source}]}


def analyse(conn, case_id, params, ctx=None) -> tuple:
    from services.phone_analysis import money_parse as MP
    from services.phone_analysis import vocabulary as V
    counts = defaultdict(int)
    phones = FV.active_phones(conn, case_id)
    ids_ = sorted(phones, key=lambda e: (str(phones[e]), e))
    vocab = None
    out = []
    win = timedelta(minutes=params["checkin_window_minutes"])
    for i, ext in enumerate(ids_):
        label = phones[ext]
        if ctx is not None:
            ctx.progress(i, len(ids_), label)
            if ctx.cancelled():
                break
        horizon = _horizon(conn, ext)
        # ---- calendar
        cal = FV.field_values(conn, ext, ("CalendarEntry",), ("Subject", "Location", "RepeatRule", "RepeatDay",
                                                              "RepeatInterval", "Account"))
        cal = _all(conn, ext, "CalendarEntry", cal)
        ct = FV.times_for(conn, ext, list(cal), ("StartDate", "EndDate", "RepeatUntil"))
        placed = _placed(conn, ext, ("planned",))
        for uid in sorted(cal):
            v = cal[uid]
            t = ct.get(uid) or {}
            start = t.get("StartDate")
            if start is None:
                counts["calendar_undated"] += 1
                continue
            end = t.get("EndDate") if t.get("EndDate") and t["EndDate"] >= start else None
            length = (end - start) if end else DEFAULT_END
            occ = occurrences(start, _first(v, "RepeatRule"), _first(v, "RepeatInterval"), t.get("RepeatUntil"),
                              _first(v, "RepeatDay"), horizon)
            counts["calendar_entries"] += 1
            counts["calendar_occurrences"] += len(occ)
            place = placed.get(uid)
            text_place = (_first(v, "Location") or "").strip() or None
            extra = {"subject": _first(v, "Subject"), "account": _first(v, "Account"),
                     "repeat_rule": _first(v, "RepeatRule"), "occurrence_count": len(occ),
                     "repeat_until": _iso(t.get("RepeatUntil")),
                     "repeat_bound": "repeat_until" if t.get("RepeatUntil") else ("phone_last_record"
                                                                                  if len(occ) > 1 else None)}
            if place is None:
                # an unplaced entry is listed once, with its occurrences counted (nothing to compare per occurrence)
                out.append(_item_result(ext, label, uid, "calendar", start, end, None, None, text_place, params,
                                        dict(extra, occurrence_count=1, occurrences=len(occ),
                                             last_occurrence=_iso(occ[-1]) if occ else None)))
                counts["calendar_text_place" if text_place else "calendar_no_place"] += 1
                continue
            counts["calendar_placed"] += 1
            for k, o in enumerate(occ):
                fixes = _fixes(conn, ext, o, o + length)
                cmp_ = compare(place, fixes, params["assumed_radius_m"])
                cmp_["synced"] = any(f["synced"] for f in fixes)
                out.append(_item_result(ext, label, uid, "calendar", o, o + length, place, cmp_, text_place, params,
                                        dict(extra, occurrence_index=k + 1)))
        # ---- check-ins
        soc = FV.field_values(conn, ext, ("SocialMediaActivity",), ("SocialActivityType", "Title", "Account"))
        checkins = {u: v for u, v in soc.items() if (_first(v, "SocialActivityType") or "").lower() == "checkin"}
        st = FV.times_for(conn, ext, list(checkins), ("TimeStamp",))
        placed_c = _placed(conn, ext, ("declared",))
        for uid in sorted(checkins):
            v = checkins[uid]
            when = (st.get(uid) or {}).get("TimeStamp")
            counts["checkins"] += 1
            if when is None:
                counts["checkins_undated"] += 1
                continue
            place = placed_c.get(uid)
            extra = {"title": _first(v, "Title"), "account": _first(v, "Account")}
            if place is None:
                counts["checkins_unplaced"] += 1
                out.append(_item_result(ext, label, uid, "checkin", when, None, None, None, None, params, extra))
                continue
            counts["checkins_placed"] += 1
            fixes = [f for f in _fixes(conn, ext, when - win, when + win) if f["record_uid"] != uid]
            cmp_ = compare(place, fixes, params["assumed_radius_m"])
            cmp_["synced"] = any(f["synced"] for f in fixes)
            out.append(_item_result(ext, label, uid, "checkin", when, None, place, cmp_, None, params, extra))
        # ---- notes
        notes = _all(conn, ext, "Note", FV.field_values(conn, ext, ("Note",), ("Title", "Body")))
        if notes and vocab is None:
            vocab = V.build(conn, case_id, ledger=True, graph=False)
        nt = FV.times_for(conn, ext, list(notes), ("Creation", "Modification"))
        for uid in sorted(notes):
            v = notes[uid]
            body = " ".join([_first(v, "Title") or "", " ".join(v["values"].get("Body", ()))]).strip()
            reading = MP.parse(body) if body else None
            hits = sorted({k for k, _ in V.matches(body, vocab)}) if body else []
            when = (nt.get(uid) or {}).get("Creation") or (nt.get(uid) or {}).get("Modification")
            counts["notes"] += 1
            supports = []
            if reading is not None and reading.amount_minor is not None:
                supports.append(_d("amount_read", "An amount is read in the note (a phone reading, never a ledger "
                                                  "row)."))
            if hits:
                supports.append(_d("case_terms", "Words matching the case: %s." % ", ".join(
                    k.replace("_", " ") for k in hits)))
            level = "moderate" if (supports and len(supports) == 2) else ("weak" if supports else "faint")
            out.append({
                "kind": "note", "strength": level,
                "measures": {"phone_label": label, "title": _first(v, "Title"),
                             "amount_minor": reading.amount_minor if reading else None,
                             "currency": reading.currency if reading else None, "case_term_kinds": hits,
                             "created": _iso(when),
                             "reasons": {"match": [s["detail"] for s in supports] or ["Nothing in the note matches an "
                                                                                       "amount or the case's names."],
                                         "substantiation": ["One note."]},
                             "rule_of_thumb": ("Notes: an amount and case words moderate, one of them weak, neither "
                                               "faint; a rule of thumb.")},
                "directions": {"supports": supports, "undercuts": []},
                "period_start": when, "period_end": when,
                "records": [{"extraction_id": ext, "record_uid": uid, "field_path": None, "role": "note"}]})
    if vocab is not None:
        counts["vocabulary_not_included"] = list(V.not_included(vocab)) + ["the case graph is not read here"]
    for r in out:
        counts["by_strength_" + r["strength"]] += 1
    if ctx is not None:
        ctx.progress(len(ids_), len(ids_))
    return out, dict(counts)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]
