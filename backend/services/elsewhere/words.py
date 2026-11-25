"""Relations, their labels, and the small pure helpers every part shares (no database here)."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from services.phone import fold as F

AGREES, DISAGREES, MISSING, POSSIBLE, NOTHING = "agrees", "disagrees", "missing_here", "possible_match", "nothing_found"
RELATIONS = (AGREES, DISAGREES, MISSING, POSSIBLE, NOTHING)
LABELS = {AGREES: "Agrees", DISAGREES: "Disagrees", MISSING: "Missing here",
          POSSIBLE: "Possible match, not confirmed", NOTHING: "Nothing found"}
ORDER = {r: i for i, r in enumerate((DISAGREES, MISSING, AGREES, POSSIBLE, NOTHING))}
PARTS = ("phones", "financial", "documents", "timeline")
PART_LABELS = {"phones": "Phones", "financial": "Financial", "documents": "Documents", "timeline": "Timeline"}

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def item(relation, text, reason, citation=None, matched_on=(), **extra) -> dict:
    assert relation in RELATIONS, relation
    out = {"relation": relation, "relation_label": LABELS[relation], "text": text, "reason": reason,
           "matched_on": sorted(set(matched_on)), "citation": citation}
    out.update(extra)
    return out


def counts(items) -> dict:
    """Possible matches are counted on their own and never added to agreement."""
    out = {AGREES: 0, DISAGREES: 0, MISSING: 0, POSSIBLE: 0}
    for it in items:
        if it["relation"] in out:
            out[it["relation"]] += 1
    return out


def sort_items(items) -> list:
    return sorted(items, key=lambda it: (ORDER[it["relation"]], it.get("_rank", 0)))


# ---- text ---------------------------------------------------------------------------------------------------------

def fold(s) -> str:
    return F.fold(s or "")


def digits(s) -> str:
    return re.sub(r"\D", "", s or "")


def number_key(s) -> str | None:
    """The last ten digits of a phone number, the part every format of it shares; ``None`` under seven digits."""
    d = digits(s)
    return d[-10:] if len(d) >= 7 else None


def identifier_key(raw):
    """``(number key, e-mail)`` for an identifier as a report prints it. A chat address that is a phone number
    (``17175550221@s.whatsapp.net``) is the number; only a real address is an e-mail."""
    raw = (raw or "").strip()
    if not raw:
        return None, None
    if "@" in raw:
        local = raw.split("@", 1)[0]
        if re.fullmatch(r"\+?\d{7,15}", local):
            return number_key(local), None
        return None, raw.lower()
    return number_key(raw), None


def words_of(s) -> list:
    return re.findall(r"[0-9a-z]+", fold(s))


def name_tokens(name) -> list:
    """The words of a person's name that identify them: brackets ("Dorian (office)") and initials dropped."""
    s = re.sub(r"\([^)]*\)", " ", name or "")
    return [w for w in words_of(s) if len(w) >= 2 and not w.isdigit()]


def name_in(name, text) -> bool:
    """Every identifying word of ``name`` is a whole word of ``text``."""
    toks = name_tokens(name)
    if not toks:
        return False
    have = set(words_of(text))
    return all(t in have for t in toks)


def strong_name(name) -> bool:
    """A name of two or more words; a single word ("Dorian", "M") alone never ties a record to a payment."""
    return len(name_tokens(name)) >= 2


# check, cheque and refund numbers; account endings
REFERENCE = re.compile(r"\b(?:check|cheque|chk|ck)\.?\s*(?:no\.?|number|#)?\s*(\d{3,8})\b", re.I)
REFUND_ID = re.compile(r"\b([A-Z]{1,3}-\d{3,6})\b")
ENDING = re.compile(r"\b(?:ending(?:\s+in)?|ends\s+in|acct\.?|account|x|\*{1,4})\s*(?:no\.?\s*)?(\d{4})\b", re.I)


def references_in(text) -> list:
    out = []
    for m in REFERENCE.finditer(text or ""):
        out.append(m.group(1))
    for m in REFUND_ID.finditer(text or ""):
        out.append(m.group(1))
    return list(dict.fromkeys(out))


def endings_in(text) -> list:
    return list(dict.fromkeys(m.group(1) for m in ENDING.finditer(text or "")))


STOP = set("""a an and are as at be been before but by can could did do does done for from get got had has have he
her here hers him his how i if in into is it its just let lets me my no not now of off ok okay on or our out please
she so that the their them then there these they this those to up us was we were what when where which who why will
with would yes you your hi hey hello thanks thank sure sorry also all any back call called come coming good great
going head made make need new one only over see some still sent send tell today tomorrow tonight yesterday well
where while yeah yep nope dear regards best""".split())
CALENDAR = set("""january february march april may june july august september october november december jan feb mar
apr jun jul aug sep sept oct nov dec monday tuesday wednesday thursday friday saturday sunday mon tue tues wed thu
thur thurs fri sat sun""".split())


def name_phrases(text) -> list:
    """Capitalised words and runs of them ("Lake Orrin", "Quarrow") that may name a person, a firm or a place. A
    common word or a month is never one; a single word must have four letters or more and not open the sentence."""
    out = []
    for sentence in re.split(r"(?<=[.!?\n])\s+", text or ""):
        run, at_start = [], True
        for i, w in enumerate(re.findall(r"[A-Za-z][A-Za-z'’-]*", sentence) + [""]):
            low = w.lower().strip("'’")
            if w and w[0].isupper() and low not in STOP and low not in CALENDAR:
                if not run:
                    at_start = i == 0
                run.append(w.strip("'’"))
                continue
            if run:
                phrase = " ".join(run)
                # a lone capitalised first word of a sentence ("After", "Thanks") is how sentences start, not a name
                if (len(run) > 1 or len(run[0]) >= 4) and not (len(run) == 1 and at_start):
                    out.append(phrase)
            run = []
    return list(dict.fromkeys(out))


def money_text(minor, currency="USD") -> str:
    sym = {"USD": "$", "GBP": "£", "EUR": "€"}.get(currency or "", "")
    whole, cents = divmod(int(minor), 100)
    s = "{:,}".format(whole) + ("." + "%02d" % cents if cents else "")
    return (sym + s) if sym else ("%s %s" % (s, currency or ""))


def money_forms(minor) -> list:
    """The ways a document prints an amount: ``2,460.00``, ``2460.00``, and ``2,460`` when it is whole."""
    whole, cents = divmod(int(minor), 100)
    forms = ["{:,}.{:02d}".format(whole, cents), "{}.{:02d}".format(whole, cents)]
    if not cents and whole >= 1000:
        forms.append("{:,}".format(whole))
    return list(dict.fromkeys(forms))


# ---- dates --------------------------------------------------------------------------------------------------------

def day_text(d) -> str:
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return "%s %d %s %d" % (WEEKDAYS[d.weekday()], d.day, MONTHS[d.month - 1], d.year)


def span_text(start, end) -> str:
    if start is None and end is None:
        return "at any date"
    if start is None:
        return "up to %s" % day_text(end)
    if end is None:
        return "from %s" % day_text(start)
    if _d(start) == _d(end):
        return "on %s" % day_text(start)
    return "between %s and %s" % (day_text(start), day_text(end))


def _d(v):
    return v.date() if isinstance(v, datetime) else v


def days_apart(a, b) -> int:
    return (_d(b) - _d(a)).days


def when_words(n) -> str:
    if n == 0:
        return "the same day"
    if n == 1:
        return "the next day"
    if n == -1:
        return "the day before"
    return "%d days %s" % (abs(n), "later" if n > 0 else "earlier")


def aware(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)


def widen(start, end, before_days, after_days):
    return (_d(start) - timedelta(days=before_days) if start else None,
            _d(end) + timedelta(days=after_days) if end else None)


def plural(n, one, many=None) -> str:
    return "%s %s" % ("{:,}".format(n), one if n == 1 else (many or one + "s"))


def join_words(xs) -> str:
    xs = [x for x in xs if x]
    if len(xs) <= 1:
        return "".join(xs)
    return ", ".join(xs[:-1]) + " and " + xs[-1]
