"""The rules that find how items could be linked, on plain data (lx-overlaps B, C).

Nothing here reads a database or calls a model. Every rule takes items (dicts, see ``services.relations.items``)
and, where a chance baseline is needed, a dict of counts read by ``sources``. Each returns *candidates* (what the
records show together) and *searched* notes (what was looked for and not found). Strength comes only from the stated
tables below, never from a model. A candidate says what occurs together, never why.

Every candidate carries ``chance``: a sentence in which the count and its base are both stated (the pattern of
``money_pairings.base_rate_words``), so a reader can see how often the same thing happens on an ordinary day.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from itertools import combinations
from math import asin, cos, radians, sin, sqrt
from typing import Any, Iterable

LEVELS = ("strong", "moderate", "weak", "faint")
LEVEL_RANK = {name: i for i, name in enumerate(LEVELS)}

# Time proximity: the gap between two dated items, and the strength that gap gives. Past a month nothing is offered.
TIME_TIERS = ((timedelta(hours=1), "strong"), (timedelta(hours=24), "moderate"),
              (timedelta(days=7), "weak"), (timedelta(days=31), "faint"))
DAY_WORDS = "dates only, no time of day"

# Place overlap: two items within each other's accuracy radius, at times this close.
PLACE_TIERS = ((timedelta(minutes=15), "strong"), (timedelta(hours=1), "moderate"),
               (timedelta(hours=6), "weak"))
# A location source no finer than this caps the strength of a place link.
SOURCE_FINENESS = {"gps": 0, "device_location": 0, "wifi": 1, "cell": 2, "celltower": 2, "other": 2}
SOURCE_CAP = {0: "strong", 1: "moderate", 2: "weak"}

RELAY_WINDOW = timedelta(minutes=10)
SILENCE_MIN = timedelta(hours=6)
CHANCE_ORDINARY = 0.25   # a link two kinds of record would make by chance on this share of days or more
CHANCE_UNUSUAL = 0.05    # and one they would make on fewer than this share of days


def weaker(a: str, b: str) -> str:
    return a if LEVEL_RANK[a] >= LEVEL_RANK[b] else b


def parse_when(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _n(value: int) -> str:
    return format(value, ",")


def kind_words(kind: str, plural: bool = True) -> str:
    words = {"financial_transaction": "payments", "phone_message": "phone messages", "phone_call": "phone calls",
             "phone_record": "phone records", "phone_location": "phone positions", "evidence": "documents",
             "graph_entity": "graph events", "timeline_event": "timeline events", "place": "places"}
    word = words.get(kind, kind.replace("_", " ") + "s")
    return word if plural else word.rstrip("s")


def base_rate_words(kind: str, days_with: int, period_days: int) -> str:
    """The count and its base, always both: "Payments are on 41 of 365 days in the period"."""
    return f"{kind_words(kind).capitalize()} are on {_n(days_with)} of {_n(period_days)} days in the period."


def chance_share(base: dict, kind_a: str, kind_b: str) -> float | None:
    """Share of days on which, if the two kinds of record were unrelated, both would have a record."""
    period = base.get("period_days") or 0
    days = base.get("days_with") or {}
    if not period or kind_a not in days or kind_b not in days:
        return None
    return (days[kind_a] / period) * (days[kind_b] / period)


def chance_reading(share: float | None) -> str:
    if share is None:
        return "No baseline: the case holds too few dated records of these kinds to say how often this happens."
    if share >= CHANCE_ORDINARY:
        return "Consistent with chance: this happens by chance on %.0f%% of days." % (share * 100)
    if share < CHANCE_UNUSUAL:
        return "Unusual: by chance both would fall on the same day on %.1f%% of days." % (share * 100)
    return "Uncommon: by chance both would fall on the same day on %.0f%% of days." % (share * 100)


def _chance_sentence(base: dict, ka: str, kb: str) -> dict:
    days = base.get("days_with") or {}
    period = base.get("period_days") or 0
    share = chance_share(base, ka, kb)
    parts = []
    for k in dict.fromkeys((ka, kb)):
        if k in days and period:
            parts.append(base_rate_words(k, days[k], period))
    return {"words": " ".join(parts + [chance_reading(share)]), "share_of_days": share,
            "reading": ("none" if share is None else "ordinary" if share >= CHANCE_ORDINARY
                        else "unusual" if share < CHANCE_UNUSUAL else "uncommon")}


def candidate(kind: str, members: list[str], key: str, strength: str, reasons: list[str], *, chance: dict | None = None,
              extra: dict | None = None) -> dict:
    out = {"kind": kind, "members": members, "key": key, "strength": strength, "reasons": reasons,
           "chance": chance or {"words": "", "reading": "none", "share_of_days": None}}
    if extra:
        out["detail"] = extra
    return out


def gap_words(delta: timedelta) -> str:
    seconds = int(abs(delta.total_seconds()))
    if seconds < 90:
        return f"{seconds} seconds"
    if seconds < 5400:
        return f"{round(seconds / 60)} minutes"
    if seconds < 172800:
        return f"{seconds / 3600:.1f} hours"
    return f"{seconds / 86400:.1f} days"


def _kind_of(item: dict) -> str:
    return item.get("time_kind") or item["type"]


# --- time proximity across any dated types (C) -------------------------------------------------------------------

def time_proximity(items: list[dict], base: dict) -> tuple[list[dict], list[dict]]:
    """Every pair of dated items inside a month of each other, strongest tier first. A pair with a date and no time of
    day is compared by day, and is never stronger than moderate."""
    cands: list[dict] = []
    searched: list[dict] = []
    dated = [(i, parse_when(i.get("at"))) for i in items]
    undated = [i["ref"] for i, at in dated if at is None]
    for (a, ta), (b, tb) in combinations([x for x in dated if x[1] is not None], 2):
        if a["ref"] == b["ref"]:
            continue
        day_precision = a.get("precision") == "day" or b.get("precision") == "day"
        gap = abs(ta - tb)
        slack = timedelta(hours=24) if day_precision else timedelta(0)
        effective = max(timedelta(0), gap - slack)
        level = next((name for limit, name in TIME_TIERS if effective <= limit), None)
        ordered = (a, b) if ta <= tb else (b, a)
        if level is None:
            searched.append({"analysis": "time_proximity", "members": [a["ref"], b["ref"]],
                             "searched": f"dates of both; gap {gap_words(gap)}; widest gap tested 31 days"})
            continue
        if day_precision:
            level = weaker(level, "moderate")
        reasons = [f"{ordered[0]['label']} comes first; {ordered[1]['label']} follows {gap_words(gap)} later."]
        if day_precision:
            reasons.append(f"One of them has a {DAY_WORDS}, so the gap is read by day.")
        cands.append(candidate("time_proximity", [a["ref"], b["ref"]], "time", level, reasons,
                               chance=_chance_sentence(base, _kind_of(a), _kind_of(b)),
                               extra={"gap_seconds": int(gap.total_seconds()), "first": ordered[0]["ref"]}))
    if undated:
        searched.append({"analysis": "time_proximity", "members": undated,
                         "searched": "no date on record, so no time was compared",
                         "out_of_reach": True})
    return cands, searched


def sequences(items: list[dict], base: dict, *, link_gap: timedelta = timedelta(days=3)) -> list[dict]:
    """Runs of three or more dated items of at least two kinds, each within ``link_gap`` of the one before: the order
    in which things happened. A run is a pattern the records show, not a reason for it."""
    dated = sorted(((parse_when(i.get("at")), i) for i in items if parse_when(i.get("at"))), key=lambda x: x[0])
    runs: list[list[tuple[datetime, dict]]] = []
    for at, item in dated:
        if runs and at - runs[-1][-1][0] <= link_gap:
            runs[-1].append((at, item))
        else:
            runs.append([(at, item)])
    out = []
    for run in runs:
        kinds = {_kind_of(i) for _, i in run}
        if len(run) < 3 or len(kinds) < 2:
            continue
        span = run[-1][0] - run[0][0]
        level = next((name for limit, name in TIME_TIERS if span <= limit * 2), "faint")
        order = " then ".join(i["label"] for _, i in run)
        out.append(candidate("sequence", [i["ref"] for _, i in run], "time", level,
                             [f"In order: {order}. The first and last are {gap_words(span)} apart."],
                             chance=_chance_sentence(base, *list(kinds)[:2]),
                             extra={"span_seconds": int(span.total_seconds()), "kinds": sorted(kinds)}))
    return out


# --- shared identifiers across types (C) -------------------------------------------------------------------------

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_DIGITS = re.compile(r"(?<![\d])(?:\+?\d[\d\s().-]{5,}\d)(?![\d])")
_SUFFIX = {"ltd", "llc", "inc", "corp", "corporation", "limited", "gmbh", "sa", "plc", "co", "company", "lp", "llp", "bv"}
_STOP = {"the", "and", "of", "for", "to", "a", "an", "in", "at", "by", "payment", "transfer", "from", "ref", "account"}
_COMPANY = re.compile(r"((?:[A-Z][\w&'-]+\s+){1,4}(?:Ltd|LLC|Inc|Corp|Corporation|Limited|GmbH|SA|PLC|LP|LLP|BV)\b\.?)")


def norm_number(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    return digits if len(digits) >= 7 else None


def name_key(raw: str) -> str:
    words = [w for w in re.sub(r"[^\w\s]", " ", (raw or "").casefold()).split() if w not in _SUFFIX]
    return " ".join(words)


def name_tokens(raw: str) -> set[str]:
    return {w for w in name_key(raw).split() if w not in _STOP and len(w) >= 4}


def extract_identifiers(text: str) -> list[dict]:
    """Emails, numbers of seven digits or more, and company names found in free text."""
    found: list[dict] = []
    for m in _EMAIL.findall(text or ""):
        found.append({"kind": "email", "value": m.lower(), "display": m})
    scrub = _EMAIL.sub(" ", text or "")
    for m in _DIGITS.findall(scrub):
        num = norm_number(m)
        if num:
            found.append({"kind": "number", "value": num, "display": m.strip()})
    for m in _COMPANY.findall(text or ""):
        key = name_key(m)
        if key:
            found.append({"kind": "name", "value": key, "display": m.strip().rstrip(".")})
    return found


def _identifier_set(item: dict) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for ident in item.get("identifiers") or []:
        kind, value = ident["kind"], ident["value"]
        if kind == "number":
            value = norm_number(value) or ""
        elif kind == "name":
            value = name_key(value)
        elif kind == "email":
            value = value.lower()
        if value:
            out[(kind, value)] = ident.get("display") or value
    for name in item.get("names") or []:
        key = name_key(name)
        if key:
            out.setdefault(("name", key), name)
    return out


def _name_match(ka: str, kb: str) -> str | None:
    if ka == kb:
        return "strong"
    ta, tb = set(ka.split()), set(kb.split())
    if not ta or not tb:
        return None
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if small <= big and len(small) >= 2:
        return "moderate"
    shared = name_tokens(ka) & name_tokens(kb)
    if shared and len(shared) >= 1 and (len(name_tokens(ka)) <= 2 or len(name_tokens(kb)) <= 2):
        return "weak"
    return None


def shared_identifiers(items: list[dict], counts) -> tuple[list[dict], list[dict]]:
    """Numbers, emails, accounts and names two items of any type both carry. ``counts(kind, value)`` says how many
    records of the case carry the same identifier, so a name on 3 rows reads differently from one on 3,000."""
    cands: list[dict] = []
    searched: list[dict] = []
    sets = {i["ref"]: _identifier_set(i) for i in items}
    for a, b in combinations(items, 2):
        sa, sb = sets[a["ref"]], sets[b["ref"]]
        hits = []
        for (ka, va), da in sa.items():
            for (kb, vb), db_ in sb.items():
                if ka != kb:
                    continue
                if ka == "name":
                    level = _name_match(va, vb)
                else:
                    level = "strong" if va == vb else None
                if level:
                    hits.append((level, ka, va, da, db_))
        if not hits:
            searched.append({"analysis": "shared_identifiers", "members": [a["ref"], b["ref"]],
                             "searched": f"{len(sa)} identifiers on {a['label']} against {len(sb)} on {b['label']}: "
                                         "numbers, emails, accounts, names",
                             "out_of_reach": not sa or not sb})
            continue
        hits.sort(key=lambda h: LEVEL_RANK[h[0]])
        level, kind, value, da, db_ = hits[0]
        c = counts(kind, value) or {}
        chance = {"words": "", "reading": "none", "share_of_days": None, "count": c.get("count"), "base": c.get("base")}
        if c.get("base"):
            chance["words"] = (f"“{da}” appears on {_n(c['count'])} of {_n(c['base'])} {c.get('unit', 'records')} in the case."
                               + (" A name this common is weak evidence." if c["count"] >= 25 and kind == "name" else ""))
            if kind == "name" and c["count"] >= 25:
                level = weaker(level, "weak")
        kind_word = {"number": "number", "email": "email address", "name": "name"}.get(kind, kind)
        reasons = [f"Both carry the same {kind_word}: “{da}” on {a['label']}, “{db_}” on {b['label']}."]
        if len(hits) > 1:
            reasons.append(f"{len(hits) - 1} more shared identifier{'s' if len(hits) > 2 else ''}.")
        cands.append(candidate("shared_identifier", [a["ref"], b["ref"]], kind, level, reasons, chance=chance,
                               extra={"identifier": value, "identifier_kind": kind, "shared": len(hits)}))
    return cands, searched


# --- place overlap with the chance beside it (C) -----------------------------------------------------------------

def haversine_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dphi, dl = p2 - p1, radians(lon2 - lon1)
    h = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * 6371000 * asin(sqrt(h))


def _fineness(source: str | None) -> int:
    key = (source or "other").casefold().replace(" ", "")
    for name, rank in SOURCE_FINENESS.items():
        if name in key:
            return rank
    return 2


def place_overlap(items: list[dict], place_stats, offsets: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Two items with a place and a time, near each other in both. Beside each: how many other phones were near the
    same place in the period, whether it is a routine place of the phone, the coarsest location source of the two, and
    whether the link survives the phones' clock offset."""
    cands: list[dict] = []
    searched: list[dict] = []
    offsets = offsets or {}
    placed = [i for i in items if i.get("place") and parse_when(i.get("at"))]
    for a, b in combinations(placed, 2):
        pa, pb = a["place"], b["place"]
        ta, tb = parse_when(a["at"]), parse_when(b["at"])
        gap = abs(ta - tb)
        dist = haversine_m(pa["lat"], pa["lon"], pb["lat"], pb["lon"])
        reach = float(pa.get("radius_m") or 0) + float(pb.get("radius_m") or 0)
        level = next((name for limit, name in PLACE_TIERS if gap <= limit), None)
        if level is None or dist > max(reach, 50.0):
            searched.append({"analysis": "place_overlap", "members": [a["ref"], b["ref"]],
                             "searched": f"positions and times of both: {round(dist)} m apart (reach {round(reach)} m), "
                                         f"{gap_words(gap)} apart in time; tested up to 6 hours"})
            continue
        fine = max(_fineness(pa.get("source")), _fineness(pb.get("source")))
        coarse_source = pa.get("source") if _fineness(pa.get("source")) >= _fineness(pb.get("source")) else pb.get("source")
        level = weaker(level, SOURCE_CAP[min(fine, 2)])
        stats = place_stats(pa["lat"], pa["lon"], max(reach, 100.0)) or {}
        words = []
        if stats.get("phones_total"):
            words.append(f"{_n(stats['phones_near'])} of {_n(stats['phones_total'])} phones in the case were within "
                         f"{round(max(reach, 100))} m of this place at some time in the period.")
        routine = False
        for ref, item in ((a["ref"], a), (b["ref"], b)):
            mine = (stats.get("days_at_place") or {}).get(item.get("phone"))
            if mine is not None and stats.get("days_active", {}).get(item.get("phone")):
                total = stats["days_active"][item["phone"]]
                words.append(f"{item['label']}: that phone was there on {_n(mine)} of {_n(total)} days it was active.")
                routine = routine or (mine / total) >= 0.25
        if routine:
            words.append("A routine place for at least one phone, so being there is ordinary.")
        offset_a, offset_b = offsets.get(a.get("phone")), offsets.get(b.get("phone"))
        if offset_a is None and offset_b is None:
            survive = "Clock offset between the phones is not known; the link holds only if the clocks agree within %s." % gap_words(
                max(timedelta(0), PLACE_TIERS[-1][0] - gap))
        else:
            shift = timedelta(seconds=abs((offset_a or 0) - (offset_b or 0)))
            held = [gap + shift, abs(gap - shift)]
            ok = min(held) <= PLACE_TIERS[-1][0]
            survive = ("The link survives the measured clock offset of %s." if ok else
                       "The link does not survive the measured clock offset of %s.") % gap_words(shift)
        reasons = [f"{a['label']} and {b['label']} are {round(dist)} m apart, {gap_words(gap)} apart in time.",
                   f"Coarsest location source: {coarse_source or 'not stated'}.", survive]
        chance = {"words": " ".join(words) or "No baseline for this place: no other position was found near it.",
                  "reading": "ordinary" if routine or (stats.get("phones_total") and stats.get("phones_near", 0) * 2 >= stats["phones_total"])
                  else "uncommon" if stats.get("phones_total") else "none", "share_of_days": None}
        cands.append(candidate("place_overlap", [a["ref"], b["ref"]], "place", level, reasons, chance=chance,
                               extra={"distance_m": round(dist), "gap_seconds": int(gap.total_seconds()),
                                      "source": coarse_source, "routine": routine}))
    if len(placed) < len([i for i in items if i.get("phone")]) or not placed:
        left = [i["ref"] for i in items if i["ref"] not in {p["ref"] for p in placed}]
        if left:
            searched.append({"analysis": "place_overlap", "members": left,
                             "searched": "items with no place or no time cannot be compared by place",
                             "out_of_reach": True})
    return cands, searched


# --- relay chains: A contacts C, then C contacts B within minutes (C) ---------------------------------------------

def relay_chains(events: list[dict], subjects: list[str], window: timedelta = RELAY_WINDOW) -> tuple[list[dict], dict]:
    """``events``: {phone, at, counterpart, direction}. A chain is one subject phone's contact with a counterpart,
    then a different subject phone's contact with the same counterpart within ``window``. Returns (candidates, count of
    events read)."""
    by_cp: dict[str, list[dict]] = {}
    for ev in events:
        if ev.get("phone") in subjects and ev.get("counterpart"):
            by_cp.setdefault(ev["counterpart"], []).append({**ev, "_t": parse_when(ev["at"])})
    out = []
    seen: set[tuple] = set()
    for cp, evs in by_cp.items():
        evs = sorted((e for e in evs if e["_t"]), key=lambda e: e["_t"])
        for i, first in enumerate(evs):
            for second in evs[i + 1:]:
                if second["_t"] - first["_t"] > window:
                    break
                if second["phone"] == first["phone"]:
                    continue
                key = (first["phone"], second["phone"], cp, first["_t"].date())
                if key in seen:
                    continue
                seen.add(key)
                gap = second["_t"] - first["_t"]
                level = "strong" if gap <= timedelta(minutes=2) else "moderate" if gap <= timedelta(minutes=5) else "weak"
                out.append(candidate("relay_chain", [first["phone"], second["phone"]], "contact", level,
                                     [f"Phone {first['label'] if first.get('label') else first['phone'][:8]} was in contact with "
                                      f"{cp} at {first['_t']:%Y-%m-%d %H:%M}; phone "
                                      f"{second['label'] if second.get('label') else second['phone'][:8]} was in contact with "
                                      f"{cp} {gap_words(gap)} later."],
                                     extra={"via": cp, "first_at": first["at"], "second_at": second["at"],
                                            "gap_seconds": int(gap.total_seconds())}))
    return out, {"events_read": sum(len(v) for v in by_cp.values())}


# --- shared silence: both quiet while otherwise active (C) -------------------------------------------------------

def silences(times: list[datetime], minimum: timedelta = SILENCE_MIN) -> list[tuple[datetime, datetime]]:
    times = sorted(times)
    return [(a, b) for a, b in zip(times, times[1:]) if b - a >= minimum]


def _overlap(a, b):
    start, end = max(a[0], b[0]), min(a[1], b[1])
    return (start, end) if end > start else None


def shared_silence(streams: dict[str, list[datetime]], minimum: timedelta = SILENCE_MIN) -> tuple[list[dict], dict]:
    """Two phones both silent for at least ``minimum`` over the same stretch. Beside it: how many of each phone's
    silences of this length there are in the period, and how many fall at the same hours (a night is ordinary
    silence). The shared silences at both phones' usual hours are one candidate per pair of phones, with every stretch
    listed in its detail; each shared silence outside their usual hours is a candidate of its own."""
    gaps = {p: silences(ts, minimum) for p, ts in streams.items()}
    out = []
    for pa, pb in combinations(sorted(gaps), 2):
        usual, unusual = [], []
        for ga in gaps[pa]:
            for gb in gaps[pb]:
                both = _overlap(ga, gb)
                if not both or both[1] - both[0] < minimum:
                    continue
                hours = (both[1] - both[0]).total_seconds() / 3600
                usual_a = sum(1 for g in gaps[pa] if _hour_overlap(g, both))
                usual_b = sum(1 for g in gaps[pb] if _hour_overlap(g, both))
                ordinary = usual_a * 2 >= max(len(gaps[pa]), 1) and usual_b * 2 >= max(len(gaps[pb]), 1)
                row = {"start": both[0].isoformat(), "end": both[1].isoformat(), "hours": round(hours, 1),
                       "usual_a": usual_a, "usual_b": usual_b}
                (usual if ordinary else unusual).append(row)
        words = (f"Phone {pa[:8]} has {_n(len(gaps[pa]))} silences of {minimum.total_seconds() / 3600:.0f} hours or more "
                 f"in the period; phone {pb[:8]} has {_n(len(gaps[pb]))}.")
        for row in unusual:
            out.append(candidate("shared_silence", [pa, pb], "time", "moderate" if row["hours"] >= 24 else "weak",
                                 [f"Both phones were silent for {row['hours']} hours from {row['start'][:16].replace('T', ' ')} "
                                  f"to {row['end'][11:16]}, outside their usual quiet hours."],
                                 chance={"words": words + f" {_n(row['usual_a'])} of the first and {_n(row['usual_b'])} of the "
                                                  "second fall at these hours.", "reading": "uncommon", "share_of_days": None},
                                 extra=row))
        if usual:
            longest = max(usual, key=lambda r: r["hours"])
            out.append(candidate("shared_silence", [pa, pb], "time", "faint",
                                 [f"Both phones were silent together {_n(len(usual))} times at their usual quiet hours; the longest was "
                                  f"{longest['hours']} hours from {longest['start'][:16].replace('T', ' ')}. Being quiet at night is ordinary."],
                                 chance={"words": words + f" All {_n(len(usual))} shared stretches fall at both phones' usual hours.",
                                         "reading": "ordinary", "share_of_days": None},
                                 extra={"stretches": usual, "count": len(usual)}))
    return out, {"silences": {p: len(g) for p, g in gaps.items()}}


def _hour_overlap(gap, other) -> bool:
    ha = {(gap[0] + timedelta(hours=h)).hour for h in range(int((gap[1] - gap[0]).total_seconds() // 3600) + 1)}
    hb = {(other[0] + timedelta(hours=h)).hour for h in range(int((other[1] - other[0]).total_seconds() // 3600) + 1)}
    return len(ha & hb) >= max(1, len(hb) // 2)


def money_amounts(items: list[dict]) -> list[dict]:
    """Payments of the same amount and currency, in the group: a link by amount (strong when to the cent)."""
    out = []
    pays = [i for i in items if i.get("amount_minor") is not None and i.get("currency")]
    for a, b in combinations(pays, 2):
        if a["currency"] == b["currency"] and abs(a["amount_minor"]) == abs(b["amount_minor"]):
            out.append(candidate("same_amount", [a["ref"], b["ref"]], "amount", "moderate",
                                 [f"Both are {a['label'].split(' · ')[1] if ' · ' in a['label'] else 'the same amount'} to the cent."],
                                 chance={"words": "", "reading": "none", "share_of_days": None}))
    return out
