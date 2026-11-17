"""Claim parser (lx-corrostatement B): a free-text sentence into who, when, where and what, as chips a person confirms.

Rules read first. A model reads only what the rules could not (``model_read``, off unless asked for). Every chip says
which of the sentence's own words it came from, how sure the reading is and whether a rule or a model made it. A chip
the sentence does not fill says so ("not stated"); one that names a place Loupe cannot place on a map says "not
located". Nothing is guessed silently: a day assumed from a phrase ("after work") is shown as the window used and
marked assumed. The reading is Loupe's, "Read by Loupe · not confirmed", until a person confirms or edits it.

Times are read in the case's zone and returned as instants. A date with no year takes the statement's year; with no
statement date a date that needs one stays unread.
"""
from __future__ import annotations

import calendar
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from services.corroborate import model as M

READ_BY = "Read by Loupe · not confirmed"
FIELDS = ("who", "when", "where", "what")
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS["sept"] = 9
WEEKDAYS = {d.lower(): i for i, d in enumerate(calendar.day_name)}
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_ORD = re.compile(rf"\b(?:the\s+)?{_DAY}(?:\s+of)?\s+({_MON})\b(?:,?\s+(\d{{4}}))?", re.I)
_MD = re.compile(rf"\b({_MON})\.?\s+{_DAY}\b(?:,?\s+(\d{{4}}))?", re.I)
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_THE_NTH = re.compile(r"\bthe\s+(\d{1,2})(?:st|nd|rd|th)\b(?!\s+of)", re.I)
_REL = re.compile(r"\b(yesterday|today|last night|this morning|this afternoon|this evening|tonight)\b", re.I)
_WEEKDAY = re.compile(rf"\b(?:last|on|on the)\s+({'|'.join(WEEKDAYS)})\b", re.I)
_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?=\W|$)", re.I)
_H24 = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_NOON = re.compile(r"\b(noon|midday|midnight)\b", re.I)
_RANGE = re.compile(r"\b(?:between|from)\s+(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\s+(?:and|to|until|till)\s+"
                    r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?", re.I)
_ABOUT = re.compile(r"\b(about|around|roughly|approximately|approx\.?|or so)\b", re.I)
# a part of the day: (words, start hour, length in hours, assumed)
PARTS = [(r"after work", 17, 3, True), (r"all evening|the whole evening|that evening|in the evening|evening", 18, 6, False),
         (r"all night|the whole night|that night|overnight|the night of|night", 22, 8, False),
         (r"all morning|in the morning|morning", 6, 6, False), (r"all afternoon|in the afternoon|afternoon", 12, 6, False),
         (r"all day|the whole day|that day", 0, 24, False), (r"lunchtime|at lunch|lunch", 12, 2, True)]
_NEG = re.compile(r"\b(did not|didn't|never|wasn't|was not|weren't|were not|not|no)\b", re.I)
_CONTACT = re.compile(r"\b(called|phoned|rang|telephoned|texted|messaged|e-?mailed|spoke to|talked to|wrote to)\b", re.I)
_WITH = re.compile(r"\b(was with|were with|met|saw|met up with|stayed with|with)\b", re.I)
_PRESENT = re.compile(r"\b(was|were|am|stayed|remained|went|drove|walked|slept|worked|in|at|on)\b", re.I)
_COORD = re.compile(r"(-?\d{1,2}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})")
_HOME = re.compile(r"\b(at home|at my home|at my house|at my place|home|indoors)\b", re.I)
_WORK = re.compile(r"\b(at work|at the office|on shift|at my desk)\b", re.I)
_I = re.compile(r"\b(I|I'm|I've|I'd|me|my)\b")
_AT_NAMED = re.compile(r"\b(?:at|in|near|outside)\s+((?:[A-Z][\w'&.-]*\s?){1,5})")
HOME_MIN_POSITIONS = 5
PLACE_RADIUS_M = 150.0


def _chip(status, value=None, words=None, confidence=None, source="rule", note=None, **extra) -> dict:
    out = {"status": status, "value": value, "words": words, "confidence": confidence, "source": source,
           "read_by": READ_BY}
    if note:
        out["note"] = note
    out.update(extra)
    return out


def _words(sentence, m) -> str:
    return sentence[m.start():m.end()].strip()


# ---- when ----------------------------------------------------------------------------------------------------------

def _resolve_month_day(day: int, month: int, year: int | None, stmt: date | None):
    """(date or None, note). A date with no year takes the statement's year, or the one before when that would put it
    after the statement."""
    if year is None:
        if stmt is None:
            return None, "the year is not stated and there is no statement date to take it from"
        year = stmt.year
        try:
            d = date(year, month, day)
        except ValueError:
            return None, "that day does not exist in that month"
        if d > stmt:
            d = date(year - 1, month, day)
            return d, f"the year is not stated: the latest {d:%d %B} before the statement ({stmt:%d %b %Y}) is used"
        return d, f"the year is not stated: {year}, the statement's year, is used"
    try:
        return date(year, month, day), None
    except ValueError:
        return None, "that day does not exist in that month"


def _find_date(s: str, stmt: date | None):
    """(date, words, note, relative-night flag) or (None, None, why, False)."""
    m = _ISO.search(s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3])), _words(s, m), None, False
        except ValueError:
            pass
    for rx, order in ((_ORD, "dm"), (_MD, "md")):
        m = rx.search(s)
        if m:
            day, month = (int(m[1]), MONTHS[m[2].lower()]) if order == "dm" else (int(m[2]), MONTHS[m[1].lower()])
            year = int(m[3]) if m[3] else None
            d, note = _resolve_month_day(day, month, year, stmt)
            return (d, _words(s, m), note, False) if d else (None, _words(s, m), note, False)
    m = _REL.search(s)
    if m:
        word = m[1].lower()
        if stmt is None:
            return None, _words(s, m), "“%s” needs the statement's date, which is not given" % word, False
        if word == "yesterday":
            return stmt - timedelta(days=1), _words(s, m), "resolved against the statement date", False
        if word == "last night":
            return stmt - timedelta(days=1), _words(s, m), "resolved against the statement date: the evening before it", True
        return stmt, _words(s, m), "resolved against the statement date", False
    m = _WEEKDAY.search(s)
    if m:
        if stmt is None:
            return None, _words(s, m), "a weekday needs the statement's date, which is not given", False
        want = WEEKDAYS[m[1].lower()]
        back = (stmt.weekday() - want) % 7 or 7
        d = stmt - timedelta(days=back)
        return d, _words(s, m), f"resolved against the statement date: the latest {m[1].title()} before it", False
    m = _THE_NTH.search(s)
    if m:
        if stmt is None:
            return None, _words(s, m), "“the %sth” needs the statement's date, which is not given" % m[1], False
        day = int(m[1])
        y, mo = stmt.year, stmt.month
        for _ in range(14):
            try:
                d = date(y, mo, day)
                if d <= stmt:
                    return d, _words(s, m), f"resolved against the statement date: the latest {d:%d %B %Y} on or before it", False
            except ValueError:
                pass
            mo -= 1
            if mo == 0:
                mo, y = 12, y - 1
        return None, _words(s, m), "no such day in the months before the statement", False
    return None, None, None, False


def _hm(h, mi, ap):
    h = int(h)
    mi = int(mi or 0)
    if ap:
        ap = ap.lower().replace(".", "")
        if h == 12:
            h = 0
        if ap.startswith("p"):
            h += 12
    return h, mi


def _find_times(s: str):
    """([(hour, minute, words)], range or None, about). A range is (start, end) as (h, m); ``about`` is a hedge."""
    rng = _RANGE.search(s)
    if rng:
        a_ap, b_ap = rng[3], rng[6]
        a_ap = a_ap or b_ap  # "between 8 and 10 pm"
        (h1, m1), (h2, m2) = _hm(rng[1], rng[2], a_ap), _hm(rng[4], rng[5], b_ap)
        if h2 * 60 + m2 <= h1 * 60 + m1 and not rng[3] and h1 < 12 and not b_ap:
            h2 += 12
        return [], ((h1, m1), (h2, m2), _words(s, rng)), False
    times, seen = [], set()
    for m in _CLOCK.finditer(s):
        h, mi = _hm(m[1], m[2], m[3])
        times.append((h, mi, _words(s, m)))
        seen.add(m.span())
    for m in _H24.finditer(s):
        if not any(a <= m.start() < b for a, b in seen):
            times.append((int(m[1]), int(m[2]), _words(s, m)))
    for m in _NOON.finditer(s):
        times.append((0, 0, _words(s, m)) if m[1].lower() == "midnight" else (12, 0, _words(s, m)))
    return times, None, bool(_ABOUT.search(s))


def _part(s: str):
    low = s.lower()
    for rx, start, length, assumed in PARTS:
        m = re.search(rf"\b(?:{rx})\b", low)
        if m:
            return (start, length, assumed, s[m.start():m.end()])
    return None


def read_when(sentence: str, stmt: date | None, zone: str) -> dict:
    tzz = M.tz(zone)
    day, day_words, day_note, rel_night = _find_date(sentence, stmt)
    times, rng, about = _find_times(sentence)
    part = _part(sentence)
    night_of = bool(re.search(r"\bnight of\b", sentence, re.I))
    if day is None:
        why = day_note or "no day is stated"
        words = " ".join(w for w in (day_words, rng[2] if rng else None, times[0][2] if times else None,
                                     part[3] if part else None) if w) or None
        return _chip("not_stated" if not day_note else "unread", None, words, None,
                     note=f"when: {why}. Give the day (the statement's date helps).", date_note=day_note)
    assumed = []
    start = end = None
    if rng:
        (h1, m1), (h2, m2), words = rng
        start = datetime.combine(day, time(h1 % 24, m1), tzz)
        end = datetime.combine(day, time(h2 % 24, m2), tzz)
        if end <= start:
            end += timedelta(days=1)
        time_words = words
    elif times:
        h, mi, time_words = times[0]
        slack = timedelta(minutes=30 if about else 15)
        base = datetime.combine(day, time(h % 24, mi), tzz)
        if (night_of or rel_night) and h < 6:
            base += timedelta(days=1)
        start, end = base - slack, base + slack
        assumed.append(f"“{time_words}” is read as {int(slack.total_seconds() // 60)} minutes either side, "
                       f"{'a hedge' if about else 'the way the engine reads one time'}")
    elif part:
        h, length, is_assumed, time_words = part
        if rel_night:
            h, length = 20, 10
        start = datetime.combine(day, time(h), tzz)
        end = start + timedelta(hours=length)
        if is_assumed:
            assumed.append(f"“{time_words}” is assumed to mean {start:%H:%M} to {end:%H:%M}")
    else:
        time_words = None
        start = datetime.combine(day, time(0), tzz)
        end = start + timedelta(hours=24)
        assumed.append("no time of day is given, so the whole day is used")
    words = " ".join(w for w in (day_words, time_words) if w)
    value = {"start": start.astimezone(timezone.utc).isoformat(), "end": end.astimezone(timezone.utc).isoformat(),
             "zone": zone, "label": f"{start:%a %d %b %Y %H:%M} to {end:%H:%M} ({zone})" if end.date() == start.date()
             else f"{start:%a %d %b %Y %H:%M} to {end:%a %d %b %H:%M} ({zone})"}
    notes = ([day_note] if day_note else []) + assumed
    conf = "low" if assumed and not times and not rng else ("medium" if day_note or assumed else "high")
    return _chip("read", value, words, conf, note="; ".join(notes) or None, assumed=bool(assumed))


# ---- who -----------------------------------------------------------------------------------------------------------

def _name_parts(people):
    first, last = {}, {}
    for p in people:
        for n in p.get("names") or []:
            w = M.name_words(n)
            if len(w) >= 2:
                first.setdefault(w[0], set()).add(p["key"])
                last.setdefault(w[-1], set()).add(p["key"])
    return first, last


def read_who(sentence: str, people: list[dict], speaker: str | None) -> dict:
    found: dict[str, tuple[str, str]] = {}
    labels = {p["key"]: p["label"] for p in people}
    for p in people:
        for n in p.get("names") or []:
            if n and M.names_match(n, sentence):
                found[p["key"]] = (n, "full name")
    low_words = set(re.findall(r"[a-z']+", sentence.lower()))
    first, last = _name_parts(people)
    for table, how in ((first, "first name"), (last, "surname")):
        for w, keys in table.items():
            if len(keys) == 1 and w in low_words:
                k = next(iter(keys))
                found.setdefault(k, (w.title(), how + " (the only person with it)"))
    digits = re.findall(r"\+?\d[\d\s().-]{6,}\d", sentence)
    for d in digits:
        num = M.norm_number(d)
        for p in people:
            if num and num in p.get("numbers", ()):
                found.setdefault(p["key"], (d.strip(), "phone number"))
    for p in people:
        for h in list(p.get("handles", ())) + list(p.get("emails", ())):
            if h and h.lower() in sentence.lower():
                found.setdefault(p["key"], (h, "handle or e-mail"))
    value, notes = [], []
    if speaker and speaker in labels and _I.search(sentence):
        value.append({"key": speaker, "label": labels[speaker], "words": "I", "how": "the person making the statement"})
    for k, (w, how) in found.items():
        if all(v["key"] != k for v in value):
            value.append({"key": k, "label": labels[k], "words": w, "how": how})
    ambiguous = sorted(w for table in (first, last) for w, keys in table.items() if len(keys) > 1 and w in low_words)
    if ambiguous:
        notes.append("“%s” matches more than one person, so it is not read" % "”, “".join(ambiguous))
    if _I.search(sentence) and not speaker:
        notes.append("“I” is not read: the speaker is not given")
    if not value:
        return _chip("not_stated", [], None, None, note="who: " + ("; ".join(notes) or "no person of the case is named") + ".")
    conf = "high" if all(v["how"] in ("full name", "phone number", "the person making the statement") for v in value) else "medium"
    return _chip("read", value, ", ".join(v["words"] for v in value), conf, note="; ".join(notes) or None)


# ---- where ---------------------------------------------------------------------------------------------------------

def read_where(sentence: str, store, who: list[dict]) -> dict:
    m = _COORD.search(sentence)
    if m:
        return _chip("read", {"name": _words(sentence, m), "lat": float(m[1]), "lon": float(m[2]),
                              "radius_m": PLACE_RADIUS_M, "located": True, "how": "coordinates in the sentence"},
                     _words(sentence, m), "high")
    known = store.known_places() if store is not None else []
    low = sentence.lower()
    for kp in known:
        key = kp["match"].lower()
        if key and key in low:
            return _place_chip(kp, kp["match"])
    for rx, kind in ((_HOME, "home"), (_WORK, "work")):
        m = rx.search(sentence)
        if m:
            speaker = who[0]["key"] if who else None
            at = store.routine_place(speaker, kind) if (store is not None and speaker) else None
            name = f"{kind} of {who[0]['label']}" if who else kind
            if at:
                return _chip("read", {"name": name, "located": True, "radius_m": at["radius_m"], "lat": at["lat"],
                                      "lon": at["lon"], "how": at["how"]}, _words(sentence, m), "medium", note=at["how"])
            addr = next((k for k in known if k.get("owner") == speaker and k.get("label", "").lower() == kind), None)
            note = f"“{_words(sentence, m)}” is {name}, but Loupe has no position for it"
            if not speaker:
                note = f"“{_words(sentence, m)}” needs to know whose {kind}: no person is named"
            return _chip("not_located", {"name": name, "located": False, "address": addr["address"] if addr else None},
                         _words(sentence, m), "low", note=note)
    m = _AT_NAMED.search(sentence)
    if m:
        name = m[1].strip()
        if name.split()[0] not in ("I", "The") or len(name.split()) > 1:
            return _chip("not_located", {"name": name, "located": False}, _words(sentence, m), "low",
                         note=f"“{name}” is named, but no place of the case has that name")
    return _chip("not_stated", None, None, None, note="where: not stated.")


def _place_chip(kp, words):
    if kp.get("lat") is not None:
        return _chip("read", {"name": kp["name"], "lat": kp["lat"], "lon": kp["lon"], "radius_m": kp["radius_m"],
                              "located": True, "how": kp["how"]}, words, "high")
    return _chip("not_located", {"name": kp["name"], "located": False, "address": kp.get("address")}, words, "low",
                 note=f"“{kp['name']}” is an address on a dossier with no position on a map")


# ---- what ----------------------------------------------------------------------------------------------------------

def read_what(sentence: str, who: list[dict], speaker: str | None) -> dict:
    neg = _NEG.search(sentence)
    negated = bool(neg)
    c = _CONTACT.search(sentence)
    if c:
        others = [w["key"] for w in who if w["key"] != speaker] if speaker else [w["key"] for w in who[1:]]
        return _chip("read", {"action": "contact", "negated": negated, "with": others, "mode": c[1].lower()},
                     _words(sentence, c) + (" (" + _words(sentence, neg) + ")" if neg else ""), "medium",
                     note=None if others else "the other person is not named")
    w = _WITH.search(sentence)
    if w and w[1].lower() != "with" or (w and len(who) >= 2):
        others = [x["key"] for x in who if x["key"] != speaker]
        return _chip("read", {"action": "with", "negated": negated, "with": others}, _words(sentence, w), "medium",
                     note=None if others else "who they were with is not named")
    p = _PRESENT.search(sentence)
    if p:
        return _chip("read", {"action": "presence", "negated": negated, "with": []}, _words(sentence, p), "medium")
    return _chip("not_stated", None, None, None, note="what: nothing to check is stated (was at, with, called).")


# ---- the whole reading ---------------------------------------------------------------------------------------------

def read_claim(store, sentence: str, *, statement_date: date | None = None, speaker: str | None = None,
               model: bool = False) -> dict:
    """The sentence as chips. ``speaker`` is the person key of whoever made the statement ("I" is theirs)."""
    sentence = " ".join(str(sentence or "").split())
    people = store.people() if store is not None else []
    zone = store.zone() if store is not None else "UTC"
    who = read_who(sentence, people, speaker)
    chips = {"who": who, "when": read_when(sentence, statement_date, zone),
             "where": read_where(sentence, store, who["value"] or []),
             "what": read_what(sentence, who["value"] or [], speaker)}
    if model:
        chips = model_read(sentence, chips, statement_date, zone, people)
    missing = [f for f in FIELDS if chips[f]["status"] != "read"]
    return {"sentence": sentence, "statement_date": statement_date.isoformat() if statement_date else None,
            "speaker": speaker, "zone": zone, "chips": chips, "missing": missing, "read_by": READ_BY}


# ---- a model, only for what rules could not read -------------------------------------------------------------------

MODEL_RULES = ("You read one sentence from a statement for an investigator. Give only what the sentence says. Answer "
               "with JSON: {\"fields\": {\"when\": {\"words\": str}, \"where\": {\"words\": str}, \"what\": "
               "{\"action\": \"presence|contact|with\", \"negated\": bool, \"words\": str}}}. Include a field only if "
               "its words are in the sentence; copy those words exactly. Never invent a date, place or person.")


def model_read(sentence, chips, stmt, zone, people):
    """Fill chips the rules left open from words the model quotes from the sentence. The words must occur in the
    sentence, or the field is dropped; a model's chip is marked ``source: model`` and confidence low."""
    open_fields = [f for f in ("when", "where", "what") if chips[f]["status"] != "read"]
    if not open_fields:
        return chips
    from services import writing_standard
    from services.llm_service import LLMService
    llm = LLMService()
    llm.system_context = writing_standard.system_prompt(MODEL_RULES, "data")
    try:
        data = json.loads(llm.call(f"Sentence: {sentence}\nFields to read: {', '.join(open_fields)}", temperature=0,
                                   json_mode=True))
    except Exception:  # noqa: BLE001 - a model that fails leaves the rules' reading as it was
        return chips
    for f in open_fields:
        got = (data.get("fields") or {}).get(f)
        if not isinstance(got, dict) or str(got.get("words") or "") not in sentence or not got.get("words"):
            continue
        if f == "what" and got.get("action") in ("presence", "contact", "with"):
            chips[f] = _chip("read", {"action": got["action"], "negated": bool(got.get("negated")), "with": []},
                             got["words"], "low", source="model")
        elif f in ("when", "where"):
            chips[f]["model_words"] = got["words"]
            chips[f]["note"] = (chips[f].get("note") or "") + f" A model points at “{got['words']}”; it is not read as a value."
    return chips
