"""Pattern grid, usual quiet hours and the nights that break them (04 section 8.2, unit U7).

Rows are local dates, columns local hours (a day with a clock change has 23 or 25). A cell carries the hour state of
5.3, the owner's interactions by strength, and how many match the grid's filter (default: interactions by the owner,
at least ``moderate``; toggles add weak, device state and physical). For a person, a cell lists each phone's state;
its state is the best across the phones and says so.

Usual quiet hours: over days with at least 12 observed hours, ``f(h)`` is the share of those days with a matching
interaction in local hour ``h``; the quiet hours are the longest circular run of hours with ``f(h) <= 0.10``, at least
3 hours long. A run covering all 24 hours means a phone observed but rarely used, not a routine (M12 on P11: 668
observed days, 51 messages): it is reported as such and never as a quiet period (04 decision 24).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from services.pattern_of_life import availability

QUIET_THRESHOLD = 0.10
MIN_QUIET_RUN = 3
MIN_OBSERVED_HOURS = 12
STRENGTH_ORDER = ("weak", "moderate", "strong")
OBSERVED_STATES = ("interaction", "data_no_interaction")
# best availability across phones, most informative first
BEST_ORDER = ("interaction", "data_no_interaction", "powered_off", "powered_off_inferred", "no_data",
              "after_extraction", "outside_selection", "not_selected")
NO_QUIET = "No regular quiet period found"
RARELY_USED = ("The phone was recording on {days} days but in use in no hour on more than 10 percent of them, so no "
               "regular quiet period can be told apart from a phone that is rarely used.")


def zone_of(name, device_zone=None):
    from zoneinfo import ZoneInfo
    if name in (None, "", "device"):
        name = device_zone or "UTC"
    if name == "UTC":
        return ZoneInfo("UTC"), "UTC"
    try:
        return ZoneInfo(name), name
    except Exception:  # noqa: BLE001
        raise ValueError("Unknown time zone %s" % name)


def local_hours(day: date, zone):
    """[(local hour label, utc start, utc end)] for one local date, 23 to 25 entries across a clock change."""
    start = datetime(day.year, day.month, day.day, tzinfo=zone).astimezone(timezone.utc)
    nxt = day + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=zone).astimezone(timezone.utc)
    out = []
    t = start
    while t < end:
        out.append((t.astimezone(zone).hour, t, min(t + timedelta(hours=1), end)))
        t += timedelta(hours=1)
    return out


def _matches(counts, min_strength, classes, include_physical):
    n = 0
    if "interaction" in classes:
        for s in STRENGTH_ORDER[STRENGTH_ORDER.index(min_strength):]:
            n += counts.get(s, 0)
    if "device_state" in classes:
        n += counts.get("device_state", 0)
    if include_physical:
        n += counts.get("physical", 0)
    return n


def grid(conn, extraction_ids, labels, start_date: date, end_date: date, zone_name="device", min_strength="moderate",
         classes=("interaction",), include_physical=False) -> dict:
    device_zone = None
    if extraction_ids:
        device_zone = conn.execute(text("SELECT device_zone FROM phone_extractions WHERE id = :e"),
                                   {"e": extraction_ids[0]}).scalar()
    zone, zname = zone_of(zone_name, device_zone)
    whole_hour = True
    days = []
    d = start_date
    span_start = datetime(start_date.year, start_date.month, start_date.day, tzinfo=zone).astimezone(timezone.utc)
    last = end_date + timedelta(days=1)
    span_end = datetime(last.year, last.month, last.day, tzinfo=zone).astimezone(timezone.utc)
    per_phone = {}
    for e in extraction_ids:
        per_phone[e] = {h["hour_utc"]: h for h in availability.hour_states(conn, e, span_start, span_end)}
    while d <= end_date:
        hours = []
        for label, a, b in local_hours(d, zone):
            if a.minute or b - a != timedelta(hours=1):
                whole_hour = False
            key = a.replace(minute=0, second=0, microsecond=0)
            phones = []
            for e in extraction_ids:
                h = per_phone[e].get(key) or {"state": "no_data", "counts": {}}
                phones.append({"extraction_id": str(e), "label": labels.get(str(e)), "state": h["state"],
                               "counts": h["counts"],
                               "match": _matches(h["counts"], min_strength, classes, include_physical)})
            best = min((p["state"] for p in phones), key=BEST_ORDER.index, default="no_data")
            counts = {}
            for p in phones:
                for k, v in p["counts"].items():
                    counts[k] = counts.get(k, 0) + v
            hours.append({"hour": label, "start": a, "state": best, "counts": counts,
                          "match": sum(p["match"] for p in phones),
                          "phones": phones})
        days.append({"date": d.isoformat(), "hours": hours})
        d += timedelta(days=1)
    quiet = quiet_hours(days)
    out = {"zone": zname, "zone_basis": "device" if zone_name in (None, "", "device") and device_zone else
           ("utc_no_device_zone" if zone_name in (None, "", "device") else "chosen"),
           "filter": {"min_strength": min_strength, "classes": list(classes), "include_physical": include_physical},
           "days": days, "quiet_hours": quiet, "breaks": [], "not_observed": []}
    if not whole_hour:
        out["zone_note"] = "This zone's offset is not a whole hour; hours are cut at the zone's own hour marks."
    if zone_name in (None, "", "device") and not device_zone:
        out["zone_note"] = "Phone time zone not recorded"
    if quiet.get("start") is not None:
        out["breaks"], out["not_observed"] = breaks(conn, extraction_ids, days, quiet, zone)
    return out


def quiet_hours(days) -> dict:
    qualifying = [dd for dd in days if sum(1 for h in dd["hours"] if h["state"] in OBSERVED_STATES)
                  >= MIN_OBSERVED_HOURS]
    if not qualifying:
        return {"start": None, "end": None, "reason": "no_observed_days", "message": NO_QUIET, "qualifying_days": 0,
                "threshold": QUIET_THRESHOLD}
    share = []
    for hh in range(24):
        hit = sum(1 for dd in qualifying if any(h["hour"] == hh and h["match"] > 0 for h in dd["hours"]))
        share.append(hit / len(qualifying))
    quiet = [s <= QUIET_THRESHOLD for s in share]
    base = {"qualifying_days": len(qualifying), "threshold": QUIET_THRESHOLD, "share_by_hour": share}
    if all(quiet):
        return dict(base, start=None, end=None, reason="rarely_used",
                    message=RARELY_USED.format(days=len(qualifying)))
    best_len, best_start = 0, None
    for s in range(24):
        if not quiet[s] or quiet[(s - 1) % 24]:
            continue
        n = 0
        while n < 24 and quiet[(s + n) % 24]:
            n += 1
        if n > best_len:
            best_len, best_start = n, s
    if best_len < MIN_QUIET_RUN:
        return dict(base, start=None, end=None, reason="no_run", message=NO_QUIET)
    return dict(base, start=best_start, end=(best_start + best_len) % 24, hours=best_len, reason=None,
                message=None)


def _in_quiet(hour, q):
    s, e = q["start"], q["end"]
    return (s <= hour < e) if s < e else (hour >= s or hour < e)


def breaks(conn, extraction_ids, days, q, zone):
    """Nights with a strong or moderate interaction inside the quiet hours, with the items; nights whose quiet hours
    were not observed at all, listed apart. A night runs from the quiet start on one date into the next."""
    brk, unseen = [], []
    by_date = {dd["date"]: dd for dd in days}
    crosses = q["start"] >= q["end"]
    for dd in days:
        night = [h for h in dd["hours"] if (h["hour"] >= q["start"] if crosses else _in_quiet(h["hour"], q))]
        if crosses:
            nxt = (date.fromisoformat(dd["date"]) + timedelta(days=1)).isoformat()
            if nxt in by_date:
                night += [h for h in by_date[nxt]["hours"] if h["hour"] < q["end"]]
            else:
                continue  # the night runs past the grid's range
        if not night:
            continue
        a = min(h["start"] for h in night)
        b = max(h["start"] for h in night) + timedelta(hours=1)
        if all(h["state"] not in OBSERVED_STATES for h in night):
            unseen.append({"date": dd["date"], "start": a, "end": b,
                           "states": sorted({h["state"] for h in night})})
            continue
        if not any(h["counts"].get("strong", 0) + h["counts"].get("moderate", 0) > 0 for h in night):
            continue
        items = [dict(r._mapping) for r in conn.execute(text(
            "SELECT id, extraction_id, record_uid, record_type, time_field, instant_utc, strength, source_app, "
            "value_key, attribution_flags FROM pol_activity_event_v WHERE extraction_id = ANY(CAST(:e AS uuid[])) AND "
            "instant_utc >= :a AND instant_utc < :b AND activity_class = 'interaction' AND counts_for = 'owner' AND "
            "strength IN ('strong','moderate') ORDER BY instant_utc"),
            {"e": [str(x) for x in extraction_ids], "a": a, "b": b})]
        brk.append({"date": dd["date"], "start": a, "end": b, "items": items, "total": len(items)})
    return brk, unseen
