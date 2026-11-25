"""Loupe's word-rule reading of a message: the checkable mentions in it, each with its kind, the words that say it,
who it is about, when and where.

This reader runs on the box and sends nothing anywhere, so it reads every phone, including a phone whose Outside
services are not allowed. A model reading (``services.mentions.model_reader``) proposes mentions in the same shape;
both are "Read by Loupe · not confirmed" until a person confirms or corrects them.

A message is split into clauses (sentence ends, and commas between two parts of three words or more). A clause gives at
most one mention: the first kind in ``PRIORITY`` whose words it holds. A question gives a mention only when it is a
plan or a meeting ("are we still on for later"), because a question asserts nothing else that could be checked.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time, timedelta, timezone

from services.mentions.kinds import READ_BY

PRIORITY = ("deleted", "money", "travel", "meeting", "home_away", "at_place", "sent", "plan")

TRIGGERS = {
    "deleted": r"\b(delete[sd]?|deleting|wiped?|erased?|got rid of)\b",
    "money": r"(\$\s?\d[\d,]*(?:\.\d\d)?|\b\d[\d,]* dollars\b|\brefunds?\b|\binvoices?\b|\bprice\b|\bpaid\b|\bpay(?:ing|ment)?\b"
             r"|\bcash\b|\b\w+ account\b|\bcheck (?:no\.? ?)?#?\d{3,}\b|\bhalf now\b|\bpayroll\b|\bdeposit(?:ed)?\b|\bwired?\b)",
    "travel": r"\b(drive|driving|drove|fly|flying|flew|flight|train to|road trip|head(?:ing)? (?:up|down|out|over|to)|"
              r"made it to|got to|arrived|landed|on my way|on the way|back on|back home|trip to|going up to|set off)\b",
    "meeting": r"\b(meet|meeting|met up|met with|see you|come to my office|come over|coming over|catch up|"
               r"still on for|who else is coming)\b",
    "home_away": r"\b(at home|home\b|in bed|asleep|sleeping|out of town|phone was off|phone off|no signal|"
                 r"not coming in|off sick|away (?:for|till|until))",
    "at_place": r"(\b(?:at|in)\s+(?:the\s+)?[A-Z][\w'’]+(?:\s+[A-Z][\w'’]+){0,3}|\bis outside\b|\bam outside\b|"
                r"\bat the (?:usual place|office|dock|cabin|lake)\b)",
    "sent": r"\b(sent|picked up|left it|dropped (?:it )?off|handed (?:it )?over|delivered|posted|e-?mailed|"
            r"leave me|got the package|goes out)\b",
    "plan": r"\b(tonight|tomorrow|later|this weekend|next week|today|minutes behind|on (?:the )?\d{1,2}(?:st|nd|rd|th)\b|"
            r"(?:mon|tues|wednes|thurs|fri|satur|sun)day|at \d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?(?!\d))",
}
_TRIG = {k: re.compile(v, re.I if k != "at_place" else 0) for k, v in TRIGGERS.items()}
_AT_PLACE_LOWER = re.compile(r"\b(?:is|am) outside\b|\bat the (?:usual place|office|dock|cabin|lake)\b", re.I)
_QUESTION_OK = ("plan", "meeting")
# a money clause is checkable when it says an amount, a check, an account or money moving, not only a topic
_MONEY_ACT = re.compile(r"(\$|\d|\b(cleared|paid|pay|paying|moving|moved|goes out|post|posted|sent|deposit|deposited|wired?|"
                        r"transfer\w*|half now|owe[sd]?)\b)", re.I)
_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")
_WORDS = re.compile(r"[\w'’$]+")
_YOU = re.compile(r"\b(you|your|you're|you'll|you've)\b", re.I)
_WE = re.compile(r"\b(we|we're|we'll|us|let's)\b", re.I)
_I = re.compile(r"\b(I|I'm|I'll|I've|I'd|me|my)\b")
_NEG = re.compile(r"\b(not|never|didn't|did not|don't|won't|wasn't|no)\b", re.I)
_AMOUNT = re.compile(r"\$\s?(\d[\d,]*)(?:\.(\d\d))?|\b(\d[\d,]*) dollars\b", re.I)
_CHECKNO = re.compile(r"\bcheck (?:no\.? ?)?#?(\d{3,})\b", re.I)
_CAPS = re.compile(r"\b([A-Z][\w'’]+(?:\s+[A-Z][\w'’]+){0,3})")
_PLACE_AFTER = re.compile(r"\b(?:at|in|to|near|up to|from)\s+(?:the\s+)?((?:[A-Z][\w'’]+)(?:\s+[A-Z][\w'’]+){0,3})")
_PLACE_THE = re.compile(r"\b(?:at|to|up to|near)\s+the\s+(lake|cabin|dock|office|usual place|beach|airport|station)\b", re.I)
_HOW = {"driving": re.compile(r"\b(drive|driving|drove|car)\b", re.I), "flying": re.compile(r"\b(fly|flying|flew|flight|landed|airport)\b", re.I),
        "train": re.compile(r"\btrain\b", re.I)}
_STOP_CAPS = {"I", "I'm", "I'll", "I've", "I'd", "IT", "OK", "Ok", "The", "A", "An", "It's", "It", "Not", "No", "Yes", "Done",
              "Please", "Can", "Did", "Are", "Is", "Who", "How", "What", "Where", "When", "Why", "Thanks", "Of", "And"}
WEEKDAYS = {d.lower(): i for i, d in enumerate(calendar.day_name)}
_MONTHS = {m.lower() for m in calendar.month_name if m}
_WEEKDAY = re.compile(r"\b(" + "|".join(WEEKDAYS) + r")\b(?:\s+(night|evening|morning|afternoon))?", re.I)
_NTH = re.compile(r"\b(?:on\s+)?the\s+(\d{1,2})(?:st|nd|rd|th)\b", re.I)
_CLOCK = re.compile(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?(?![\d:])", re.I)
_PARTS = {"tonight": (18, 6), "this evening": (18, 6), "this morning": (6, 6), "this afternoon": (12, 6)}
MINUTE = timedelta(minutes=1)
_FUTURE = re.compile(r"\b(will|'ll|’ll|going to|gonna|before you|before I|heading|head up|head out|planning|next)\b", re.I)


def _tz(zone):
    from services.corroborate import model as M
    return M.tz(zone)


def clauses(body: str) -> list[tuple[int, int]]:
    """Clause spans of the body: sentence ends, then a comma between two parts of three words or more, or before a
    question ("at the market, want anything?": the statement and the question are read apart)."""
    out = []
    pos = 0
    for part in _SPLIT.split(body or ""):
        if not part:
            continue
        start = body.index(part, pos)
        pos = start + len(part)
        pieces, s = [], 0
        for m in re.finditer(r",\s+", part):
            left, right = part[s:m.start()], part[m.end():]
            nl, nr = len(_WORDS.findall(left)), len(_WORDS.findall(right))
            if (nl >= 3 and nr >= 3) or (nl >= 2 and right.rstrip().endswith("?")):
                pieces.append((s, m.start()))
                s = m.end()
        pieces.append((s, len(part)))
        for a, b in pieces:
            seg = part[a:b]
            lead = len(seg) - len(seg.lstrip())
            seg = seg.strip().rstrip(",;.!")
            if seg:
                out.append((start + a + lead, start + a + lead + len(seg)))
    return out


def _is_question(body, end):
    rest = body[end:end + 2]
    return rest.startswith("?")


def _person_named(clause, people, exclude=()):
    low = clause.lower()
    for p in people:
        for n in list(p.get("names") or []):  # names a person is known by, never a placeholder label
            if not n or p["key"] in exclude:
                continue
            first = n.split()[0]
            if len(first) >= 3 and re.search(rf"\b{re.escape(first.lower())}\b", low):
                return p["key"]
    return None


def _amounts(clause):
    out = []
    for m in _AMOUNT.finditer(clause):
        whole = (m.group(1) or m.group(3) or "0").replace(",", "")
        out.append(int(whole) * 100 + int(m.group(2) or 0))
    return out


def content_words(clause, people) -> list[str]:
    """Capitalised names and the money words a payment or document could carry ("Quarrow", "Lake Orrin")."""
    names = {w.lower() for p in people for n in list(p.get("names") or []) if n for w in n.split()}
    out = []
    for m in _CAPS.finditer(clause):
        run_ = []
        for x in m.group(1).split() + [None]:
            if x is None or x in _STOP_CAPS or x.lower() in names or x.lower() in WEEKDAYS or x.lower() in _MONTHS:
                if run_ and (m.start() > 0 or len(run_) > 1):
                    out.append(" ".join(run_))
                run_ = []
            else:
                run_.append(x)
    for m in re.finditer(r"\b(\w+) account\b", clause, re.I):
        if m.group(1).lower() not in ("the", "my", "your", "an", "a", "that", "this"):
            out.append(m.group(1))
    return list(dict.fromkeys(w for w in out if len(w) >= 3))


def _local_day(at, zone):
    return at.astimezone(_tz(zone)).date()


def _window(day: date, h0: int, hours: float, zone) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(h0 % 24), _tz(zone))
    return start.astimezone(timezone.utc), (start + timedelta(hours=hours)).astimezone(timezone.utc)


def read_when(clause: str, at: datetime, zone: str, kind: str) -> dict:
    """The window a clause points at, read forward from the message's own time (a message plans ahead or reports
    the present). When the clause names no time, the window is the message's own moment, sized for the kind."""
    lo = hi = None
    words, assumed = None, None
    today = _local_day(at, zone)
    local = at.astimezone(_tz(zone))
    m = _WEEKDAY.search(clause)
    n = _NTH.search(clause)
    c = _CLOCK.search(clause)
    rel = next((x for x in re.finditer(r"\b(tonight|this evening|this morning|this afternoon|tomorrow|today|this weekend|later)\b",
                                       clause, re.I) if not re.search(r"\bnot\s+$", clause[:x.start()], re.I)), None)
    day = None
    if m:
        wd = WEEKDAYS[m.group(1).lower()]
        ahead = (wd - today.weekday()) % 7
        day = today + timedelta(days=ahead)
        words = m.group(0)
        part = (m.group(2) or "").lower()
        if part in ("night", "evening"):
            lo, hi = _window(day, 18, 10 if part == "night" else 6, zone)
        elif part == "morning":
            lo, hi = _window(day, 6, 6, zone)
        elif part == "afternoon":
            lo, hi = _window(day, 12, 6, zone)
        if ahead == 0 and not part:
            assumed = f"“{m.group(1)}” is read as the day the message was sent"
    elif n:
        d = int(n.group(1))
        y, mo = today.year, today.month
        for _ in range(3):
            try:
                cand = date(y, mo, d)
            except ValueError:
                cand = None
            if cand and cand >= today:
                day = cand
                break
            mo = mo % 12 + 1
            y += 1 if mo == 1 else 0
        words = n.group(0)
    elif rel:
        r = rel.group(1).lower()
        words = rel.group(0)
        if r in _PARTS:
            h, length = _PARTS[r]
            day = today
            lo, hi = _window(today, h, length, zone)
        elif r == "tomorrow":
            day = today + timedelta(days=1)
        elif r == "today":
            day = today
        elif r == "this weekend":
            sat = today + timedelta(days=(5 - today.weekday()) % 7)
            lo, hi = _window(sat, 0, 48, zone)
            day = sat
        elif r == "later":
            lo, hi = at, at + timedelta(hours=8)
            assumed = "“later” is read as the eight hours after the message"
    if c:
        h, mi, ap = int(c.group(1)), int(c.group(2) or 0), (c.group(3) or "").lower().replace(".", "")
        if h <= 12:
            if ap == "pm" and h < 12:
                h += 12
            elif ap == "am" and h == 12:
                h = 0
        words = " ".join(x for x in (words, c.group(0)) if x)
        base_day = day or today
        cand = datetime.combine(base_day, time(h % 24, mi), _tz(zone))
        if not ap and h < 12:
            # "at 9", "at 7": the next 9 o'clock or 7 o'clock after the message, morning or evening
            opts = [cand, cand + timedelta(hours=12), cand + timedelta(days=1)] if not day else [cand, cand + timedelta(hours=12)]
            nxt = [o for o in opts if o >= local - timedelta(minutes=30)]
            cand = nxt[0] if nxt else cand
            assumed = f"“{c.group(0)}” is read as the next {cand:%H:%M} after the message"
        elif not day and cand < local - timedelta(minutes=30):
            cand += timedelta(days=1)
        lo, hi = (cand - timedelta(minutes=30)).astimezone(timezone.utc), (cand + timedelta(minutes=60)).astimezone(timezone.utc)
    if lo is None and day is not None:
        lo, hi = _window(day, 0, 24, zone)
    if lo is None:
        # no time named: the message's own moment
        span = {"travel": (timedelta(hours=1), timedelta(hours=3)), "at_place": (timedelta(minutes=30), timedelta(minutes=30)),
                "home_away": (timedelta(hours=1), timedelta(hours=1)), "meeting": (timedelta(minutes=30), timedelta(hours=2)),
                }.get(kind, (timedelta(hours=1), timedelta(hours=1)))
        if kind == "home_away" and re.search(r"\b(phone was off|phone off|no signal)\b", clause, re.I):
            span = (timedelta(hours=3), timedelta(0))
        if kind == "home_away" and re.search(r"\b(not coming in|off sick|off work)\b", clause, re.I):
            lo, hi = _window(today, 8, 10, zone)
            assumed = "not coming in is read as 8 am to 6 pm on the day of the message"
        elif kind == "home_away" and re.search(r"\ball day\b", clause, re.I):
            lo, hi = _window(today, 8, 14, zone)
            assumed = "“all day” is read as 8 am to 10 pm on the day of the message"
        elif kind == "travel" and _FUTURE.search(clause) and not re.search(r"\b(on my way|on the way)\b", clause, re.I):
            lo, hi = at, at + timedelta(days=3)
            assumed = "a trip ahead with no time named is read as the three days after the message"
        else:
            lo, hi = at - span[0], at + span[1]
            assumed = "no time is named, so the time around the message is used"
        words = None
    zone_label = f"{lo.astimezone(_tz(zone)):%a %d %b %Y %H:%M} to " + (
        f"{hi.astimezone(_tz(zone)):%H:%M}" if lo.astimezone(_tz(zone)).date() == hi.astimezone(_tz(zone)).date()
        else f"{hi.astimezone(_tz(zone)):%a %d %b %H:%M}")
    return {"start": lo.isoformat(), "end": hi.isoformat(), "zone": zone, "label": zone_label, "words": words,
            "assumed": assumed}


def read_where(clause: str, kind: str, known: list[dict]) -> dict | None:
    low = clause.lower()
    for kp in sorted(known or [], key=lambda k: -len(k.get("match") or "")):
        mt = (kp.get("match") or "").strip()
        if len(mt) >= 3 and re.search(rf"\b{re.escape(mt.lower())}\b", low):
            out = {"name": kp["name"], "words": mt, "located": kp.get("lat") is not None, "how": kp.get("how")}
            if out["located"]:
                out.update({"lat": kp["lat"], "lon": kp["lon"], "radius_m": kp.get("radius_m") or 150.0})
            return out
    if re.search(r"\b(at home|home\b|in bed|asleep|unpacking)", clause, re.I) and kind in ("home_away", "travel", "at_place"):
        return {"name": "home", "words": "home", "routine": "home", "located": False}
    if re.search(r"\b(office|at work)\b", clause, re.I):
        return {"name": "work", "words": "office" if "office" in low else "at work", "routine": "work", "located": False}
    m = _PLACE_AFTER.search(clause)
    if m and m.group(1).split()[0] not in _STOP_CAPS:
        return {"name": m.group(1), "words": m.group(1), "located": False}
    m = _PLACE_THE.search(clause)
    if m:
        return {"name": "the " + m.group(1).lower(), "words": m.group(0), "located": False}
    if re.search(r"\b(?:is|am) outside\b", clause, re.I):
        return {"name": "outside", "words": "outside", "near_counterpart": True, "located": False}
    return None


def _kind_of(clause: str, question: bool):
    for k in PRIORITY:
        if question and k not in _QUESTION_OK:
            continue
        m = _TRIG[k].search(clause)
        if not m:
            continue
        if k == "at_place" and not _AT_PLACE_LOWER.search(clause):
            # "at/in" + a capitalised word: not a time, a weekday or a person-like word
            pl = _PLACE_AFTER.search(clause)
            if not pl or pl.group(1).split()[0] in _STOP_CAPS or pl.group(1).lower() in WEEKDAYS:
                continue
        if k == "money" and not _MONEY_ACT.search(clause):
            continue
        if k == "plan" and question and not re.search(r"\b(still on|later|tonight|tomorrow)\b", clause, re.I):
            continue
        return k, m
    return None, None


def read_message(body: str, *, at: datetime, zone: str, speaker: str | None, addressee: list[str],
                 people: list[dict], known: list[dict]) -> list[dict]:
    """The mentions in one message, each a reading with its span in ``body``."""
    out = []
    for a, b in clauses(body or ""):
        clause = body[a:b]
        q = _is_question(body, b) or clause.endswith("?")
        kind, m = _kind_of(clause, q)
        if not kind:
            continue
        who_words = "I"
        if kind == "meeting":
            who, who_words = ([speaker] if speaker else []), "I"
        elif _YOU.search(clause) and not _I.search(clause):
            who, who_words = list(addressee), "you"
        elif _WE.search(clause):
            who, who_words = [k for k in [speaker] + list(addressee) if k], "we"
        else:
            named = _person_named(clause, people, exclude=[speaker] + list(addressee))
            who = [named] if named and kind not in ("meeting",) else ([speaker] if speaker else [])
            who_words = "named" if named and kind != "meeting" else "I"
        with_ = []
        if kind in ("meeting", "plan", "sent") or (kind == "at_place" and re.search(r"outside", clause, re.I)):
            with_ = [k for k in addressee if k not in who]
        out.append({
            "kind": kind, "phrase": clause, "start": a, "end": b, "trigger": m.group(0),
            "question": q, "negated": bool(_NEG.search(clause)),
            "who": [k for k in who if k], "who_words": who_words, "with": with_,
            "when": read_when(clause, at, zone, kind),
            "where": read_where(clause, kind, known),
            "how": next((h for h, rx in _HOW.items() if rx.search(clause)), None) if kind == "travel" else None,
            "amounts_minor": _amounts(clause), "check_numbers": _CHECKNO.findall(clause),
            "words": content_words(clause, people),
            "reader": "rules", "read_by": READ_BY,
        })
    return out
