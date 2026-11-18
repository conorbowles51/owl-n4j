"""The link model of Corroborate on plain data (lx-corroengine B, D): people, records, instances and the comparison set.

Nothing here reads a database or calls a model; ``store`` reads the case and hands these functions plain dicts, and
the tests do the same with invented data.

People. Every record joins to people through what identifies them: phone numbers, app handles, e-mail addresses,
bank accounts, names. A person is ``{key, label, numbers, handles, emails, accounts, names, phones, links}``. Each
entry of ``links`` says how one identifier was tied to the person and whether a person recorded it (``recorded``)
or Loupe suggests it (``suggested``, with its basis), so a suggested link is never shown as an established one.

Records. ``{ref, kind, at, day_only, phone, owner, parties, counterpart_values, thread, app, body, place, amount_minor,
dup_key, source, deleted}``. ``kind`` is one of RECORD_KINDS. ``at`` is a timezone-aware instant (UTC); a record known
only to the day has ``day_only``.

Instances. One instance is one stretch of time the question is asked about (an incident night) or compared with (an
ordinary night): ``{id, side, label, start, end, money_end, weekday}``. Times of day are read in the case's zone and
the zone is named in every label.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

RECORD_KINDS = ("message", "call", "email", "position", "media_position", "payment", "payment_alert", "doc_row",
                "activity")
CONTACT_KINDS = ("message", "call", "email")
MONEY_KINDS = ("payment", "payment_alert")

CLUSTER_GAP = timedelta(hours=12)       # selected records further apart than this are separate instances
MONEY_SPREAD = timedelta(days=3)        # money is read up to this long after an instance ends
PAD = timedelta(hours=2)                # an instance's hours are the selection's hours with this much either side
SEED_SPREAD = timedelta(hours=6)        # a single instance from one stretch of records: this much either side
MAX_WINDOW = timedelta(hours=30)
RELAY_WINDOW = timedelta(minutes=10)    # A contacts X, X contacts B within this: contact through a third number
TOGETHER_GAP = timedelta(minutes=15)    # two positions this close in time ...
TOGETHER_SLACK_M = 50.0                 # ... and within their accuracy radii plus this many metres
TOGETHER_MAX_RADIUS_M = 2_000.0         # a position coarser than this never places two people together
SILENCE_MIN = timedelta(hours=4)        # a phone with nothing at all for this long inside the hours asked about
STRUCTURING_BELOW_MINOR = 1_000_000     # cash deposits just under $10,000 ...
STRUCTURING_FROM_MINOR = 900_000        # ... from $9,000


def tz(zone: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(zone or "UTC")
    except Exception:  # noqa: BLE001 - an unknown zone name reads as UTC, and the label says UTC
        return ZoneInfo("UTC")


def norm_number(raw: str | None) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10:  # a North American number written without its country code
        digits = "1" + digits
    return digits if len(digits) >= 7 else None


def name_words(raw: str | None) -> list[str]:
    return [w for w in re.sub(r"[^\w\s]", " ", (raw or "").casefold()).split() if len(w) >= 2]


def names_match(full_name: str, text: str) -> bool:
    """A person's full name appears in a text, in either order ("Jane Doe", "DOE, JANE"); a first name or a
    surname alone never matches (another person may share it)."""
    words = name_words(full_name)
    if len(words) < 2:
        return False
    hay = set(name_words(text))
    return all(w in hay for w in words)


# ---- people --------------------------------------------------------------------------------------------------------

def person_for_value(people: list[dict], value: str | None) -> str | None:
    """The person whose number, handle or e-mail this is."""
    if not value:
        return None
    v = value.strip().lower()
    num = norm_number(v) if "@" not in v else None
    for p in people:
        if v in p.get("handles", ()) or v in p.get("emails", ()):
            return p["key"]
        if "@s.whatsapp.net" in v and norm_number(v.split("@")[0]) in p.get("numbers", ()):
            return p["key"]
        if num and num in p.get("numbers", ()):
            return p["key"]
    return None


def person_for_name(people: list[dict], text: str) -> str | None:
    hits = [p["key"] for p in people if any(names_match(n, text) for n in p.get("names", ()) if n)]
    return hits[0] if len(hits) == 1 else None


# ---- instances -----------------------------------------------------------------------------------------------------

def _local(at: datetime, zone: ZoneInfo) -> datetime:
    return at.astimezone(zone)


def cluster(points: list[dict]) -> list[list[dict]]:
    """Group the selection's dated records into stretches. Money records join the stretch that ended within
    MONEY_SPREAD before them; otherwise they make their own."""
    timed = sorted((p for p in points if p.get("at") and p.get("kind") not in MONEY_KINDS), key=lambda p: p["at"])
    groups: list[list[dict]] = []
    for p in timed:
        if groups and p["at"] - groups[-1][-1]["at"] <= CLUSTER_GAP:
            groups[-1].append(p)
        else:
            groups.append([p])
    for p in sorted((p for p in points if p.get("at") and p.get("kind") in MONEY_KINDS), key=lambda p: p["at"]):
        home = None
        for g in groups:
            end = max(x["at"] for x in g)
            if timedelta(0) <= p["at"] - end <= MONEY_SPREAD or (p.get("day_only") and abs(p["at"] - end) <= MONEY_SPREAD):
                home = g
        if home is not None:
            home.append(p)
        else:
            groups.append([p])
    return sorted(groups, key=lambda g: min(x["at"] for x in g))


def _hours_of(groups: list[list[dict]], zone: ZoneInfo) -> tuple[time, timedelta]:
    """The local start time and length of the hours the stretches cover, padded; a single stretch gets the wider seed
    spread. Midnight-crossing hours are kept as one span."""
    starts, lengths = [], []
    for g in groups:
        timed = [x for x in g if not x.get("day_only") and x.get("kind") not in MONEY_KINDS] or \
                [x for x in g if not x.get("day_only")]
        if not timed:
            continue
        lo, hi = min(x["at"] for x in timed), max(x["at"] for x in timed)
        starts.append(_local(lo, zone))
        lengths.append(hi - lo)
    if not starts:
        return time(0, 0), timedelta(hours=24)
    pad = SEED_SPREAD if len(starts) == 1 else PAD
    # each start as minutes after noon, so evenings and the small hours after them order together
    mins = [((s.hour * 60 + s.minute) - 720) % 1440 for s in starts]
    first = min(mins)
    span = max(m + length.total_seconds() / 60 for m, length in zip(mins, lengths)) - first
    start_min = (first + 720 - pad.total_seconds() / 60) % 1440
    length = min(timedelta(minutes=span) + 2 * pad, MAX_WINDOW)
    return time(int(start_min // 60), int(start_min % 60)), length


def _anchor_day(g: list[dict], start: time, zone: ZoneInfo) -> date:
    """The local day on which the stretch's hours start."""
    timed = [x for x in g if not x.get("day_only") and x.get("kind") not in MONEY_KINDS] or g
    first = _local(min(x["at"] for x in timed), zone)
    day = first.date()
    if datetime.combine(day, start, zone) > first:
        day -= timedelta(days=1)
    return day


def make_instance(day: date, start: time, length: timedelta, zone: ZoneInfo, side: str, zone_name: str) -> dict:
    s = datetime.combine(day, start, zone)
    e = s + length
    return {"id": f"{day.isoformat()}", "side": side, "day": day.isoformat(), "weekday": day.strftime("%A"),
            "start": s.astimezone(timezone.utc), "end": e.astimezone(timezone.utc),
            "money_end": e.astimezone(timezone.utc) + MONEY_SPREAD,
            "label": f"{day:%a %d %b %Y} {s:%H:%M}-{e:%H:%M} ({zone_name})"}


def incidents_from_selection(points: list[dict], zone_name: str) -> tuple[list[dict], dict]:
    zone = tz(zone_name)
    groups = cluster(points)
    if not groups:
        return [], {"start": None, "length_h": 0}
    start, length = _hours_of(groups, zone)
    days = sorted({_anchor_day(g, start, zone) for g in groups})
    return ([make_instance(d, start, length, zone, "incident", zone_name) for d in days],
            {"start": start.strftime("%H:%M"), "length_h": round(length.total_seconds() / 3600, 1)})


COMPARISON_KINDS = ("same_weekday_hours", "same_people_ordinary", "before_after", "group_vs_group")


def comparison_set(kind: str, incidents: list[dict], period: tuple[date, date] | None, zone_name: str,
                   hours: dict, *, after: date | None = None) -> tuple[list[dict], dict]:
    """Ordinary instances built from the incidents (Q), and the words that state the comparison.

    ``same_weekday_hours``: the same weekday and hours in every other week of the period (all incidents on one
    weekday), else the same hours on every other day. ``same_people_ordinary``: the same hours on every other day of
    the period. ``before_after``: incidents are the days on and after ``after``, ordinary the days before it."""
    zone = tz(zone_name)
    if not incidents or not period:
        return [], {"kind": kind, "words": "No period with records to compare with.", "incident_noun": "instances",
                    "ordinary_noun": "ordinary instances"}
    lo, hi = period
    if kind == "group_vs_group":
        # the other group is compared on the same instances: no ordinary instances (the engine fills the counts)
        return [], {"kind": kind, "words": "", "incident_noun": "instances asked about" if len(incidents) > 1 else
                    "instance asked about", "ordinary_noun": "pair-instances in the other group"}
    h, m = (int(x) for x in hours["start"].split(":"))
    length = timedelta(hours=hours["length_h"])
    taken = {i["day"] for i in incidents}
    weekdays = {date.fromisoformat(i["day"]).weekday() for i in incidents}
    if kind == "same_weekday_hours" and len(weekdays) != 1:
        kind = "same_people_ordinary"
    days = [lo + timedelta(days=n) for n in range((hi - lo).days + 1)]
    if kind == "same_weekday_hours":
        wd = next(iter(weekdays))
        days = [d for d in days if d.weekday() == wd]
        day_name = date.fromisoformat(incidents[0]["day"]).strftime("%A")
        inc_noun, ord_noun = f"incident {day_name}s" if len(incidents) > 1 else f"{day_name} asked about", \
            f"other {day_name}s"
        words = (f"Compared with the same hours ({hours['start']}, {hours['length_h']:g} h, {zone_name}) on every "
                 f"other {day_name} from {lo:%d %b %Y} to {hi:%d %b %Y} that has records.")
    elif kind == "before_after" and after:
        inc_noun, ord_noun = "days on or after", "days before"
        words = f"The days on and after {after:%d %b %Y} compared with the days before it, from {lo:%d %b %Y} to {hi:%d %b %Y}."
    else:
        kind = "same_people_ordinary"
        inc_noun = "instances asked about" if len(incidents) > 1 else "instance asked about"
        ord_noun = "ordinary days"
        words = (f"Compared with the same people in the same hours ({hours['start']}, {hours['length_h']:g} h, "
                 f"{zone_name}) on every other day from {lo:%d %b %Y} to {hi:%d %b %Y} that has records.")
    ordinary = [make_instance(d, time(h, m), length, zone, "ordinary", zone_name) for d in days
                if d.isoformat() not in taken and all(abs((d - date.fromisoformat(t)).days) >= 1 for t in taken)]
    return ordinary, {"kind": kind, "words": words, "incident_noun": inc_noun, "ordinary_noun": ord_noun}


# A phone covers the stretches of days on which it holds records: record days at most COVER_GAP_DAYS apart join one
# stretch, and a stretch of fewer than COVER_MIN_DAYS record days is set aside (a clock error such as a 1970 or 2057
# date, or a lone record far from the rest). Setting one aside only turns "absent" into "no data", never the reverse.
COVER_GAP_DAYS = 14
COVER_MIN_DAYS = 3


def phone_spans(days: list[date]) -> tuple[list[tuple[datetime, datetime]], int]:
    """(spans as UTC datetimes from the first day's start to the last day's end, record days set aside)."""
    days = sorted(set(days))
    runs: list[list[date]] = []
    for d in days:
        if runs and (d - runs[-1][-1]).days <= COVER_GAP_DAYS:
            runs[-1].append(d)
        else:
            runs.append([d])
    kept = [r for r in runs if len(r) >= COVER_MIN_DAYS]
    spans = [(datetime.combine(r[0], time.min, timezone.utc), datetime.combine(r[-1], time.max, timezone.utc))
             for r in kept]
    return spans, sum(len(r) for r in runs if len(r) < COVER_MIN_DAYS)


def in_window(rec: dict, inst: dict, *, money: bool = False) -> bool:
    end = inst["money_end"] if money else inst["end"]
    if rec.get("day_only"):
        d = rec["at"].date()
        return inst["start"].date() <= d <= end.date()
    return inst["start"] <= rec["at"] <= end


# ---- small helpers -------------------------------------------------------------------------------------------------

def haversine_m(lat1, lon1, lat2, lon2) -> float:
    from math import asin, cos, radians, sin, sqrt
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = p2 - p1, radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * 6_371_000 * asin(sqrt(a))


def pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def dedupe(records: Iterable[dict]) -> tuple[list[dict], int]:
    """Copies of one record count once: the same message held on two phones (same text, same minute), the same
    payment as a ledger row and as alerts on the phones (same amount, same day, same people). Returns the kept
    records (each with ``copies``: the refs folded into it) and how many copies were folded."""
    kept: dict[tuple, dict] = {}
    folded = 0
    for r in records:
        key = r.get("dup_key")
        if key is None:
            kept[("ref", r["ref"])] = {**r, "copies": [r["ref"]]}
            continue
        if key in kept:
            kept[key]["copies"].append(r["ref"])
            folded += 1
        else:
            kept[key] = {**r, "copies": [r["ref"]]}
        # whose phone deleted its copy and whose kept it (a deletion another phone kept is a signal, lx-leads D)
        if r.get("owner"):
            side = "deleted_by" if r.get("deleted") else "kept_by"
            if r["owner"] not in kept[key].setdefault(side, []):
                kept[key][side].append(r["owner"])
    return list(kept.values()), folded


_WORD = re.compile(r"[\w'$.,]+", re.UNICODE)


def phrases(body: str | None, n: int = 3) -> set[str]:
    """Word runs of ``n`` (lower case) in a text: what "the same words" means between two records."""
    words = [w.strip(".,").casefold() for w in _WORD.findall(body or "")]
    words = [w for w in words if w]
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)} if len(words) >= n else set()


def fmt_money(minor: int | None, currency: str | None = "USD") -> str:
    if minor is None:
        return "an amount"
    sign = "$" if (currency or "USD") == "USD" else ((currency or "") + " ")
    return f"{sign}{abs(minor) / 100:,.2f}"


def iso(at: datetime | None) -> str | None:
    return at.isoformat() if at else None


def as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, 12, tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            v = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    return None
