"""Understand the question before searching (plan R2a).

- Terms: ``chat_retrieval.terms`` (quoted phrases, numbers as a phone prints them, words of 3+ letters that are not
  common words, longest first).
- Names: each capitalised word or word pair of the question is looked up among the case's phone contact names, phone
  identities and bank account holders. A match adds the identity's number or handle, the other names the phones give
  it, and the account number, as extra search terms. Each expansion says where the tie comes from; none is a person's
  confirmation unless the case's link says so.
- Dates: a day, a span of days or a month written in the question becomes a window from local midnight to local
  midnight in the case's time zone (``streams.case_zone``), stated as UTC instants. The window ranks results inside it
  higher (the reranker sees it); it never filters, because a message about a night can be sent on another day.
- Phrasings: other ways to say the question (``rerank.phrasings``, a model call), searched by meaning beside it.
"""
from __future__ import annotations

import calendar
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

MAX_EXPANSIONS = 12
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS["sept"] = 9
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_YEAR = r"((?:19|20)\d\d)"
ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# "12 April 2024", "12-13 April", "12 to 13 April 2024"
DAY_MON = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?(?:\s*(?:-|–|to|and)\s*(\d{1,2})(?:st|nd|rd|th)?)?\s+" + _MON
                     + r"\.?(?:,?\s+" + _YEAR + r")?\b", re.I)
# "April 12, 2024", "April 12-13"
MON_DAY = re.compile(r"\b" + _MON + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*(?:-|–|to)\s*(\d{1,2}))?(?:,?\s+" + _YEAR
                     + r")?\b", re.I)
# "April 2024"
MON_YEAR = re.compile(r"\b" + _MON + r"\.?\s+" + _YEAR + r"\b", re.I)
# "between 23 May and 7 June 2024"
BETWEEN = re.compile(r"\b(?:between|from)\s+(\d{1,2})(?:st|nd|rd|th)?\s+" + _MON + r"(?:\s+" + _YEAR
                     + r")?\s+(?:and|to|until|-)\s+(\d{1,2})(?:st|nd|rd|th)?\s+" + _MON + r"(?:\s+" + _YEAR + r")?",
                     re.I)
NAME = re.compile(r"\b([A-Z][a-z'’]{2,}(?:\s+[A-Z][a-z'’]{2,})*)\b")
NOT_NAMES = frozenset("""The This That These Those What When Where Which Who Whom Whose Why How Did Does Was Were Is Are
Has Have Had Can Could Would Should Will Find Show List Give Tell Search Look Any Every All Each Between From Phone
Phones Message Messages Call Calls Payment Payments Account Accounts Bank Statement Statements Document Documents
Night Day Week Month Year Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May
June July August September October November December Also After Before During About Report Summary Please""".split())


def _month(word: str) -> int:
    return MONTHS[word.lower().rstrip(".")[:4] if word.lower().startswith("sept") else word.lower().rstrip(".")[:3]
                  if word.lower()[:3] in MONTHS else word.lower()]


def _years(question: str) -> list[int]:
    return [int(y) for y in re.findall(r"\b((?:19|20)\d\d)\b", question)]


def date_spans(question: str) -> list[tuple[date, date, str]]:
    """Every day, span of days or month written in the question: ``(first day, last day, as written)``. A day with
    no year takes the question's only year; with none or several, it is left out (said in ``windows``' notes)."""
    q = question or ""
    years = sorted(set(_years(q)))
    only = years[0] if len(years) == 1 else None
    out: list[tuple[date, date, str]] = []
    used: list[tuple[int, int]] = []

    def add(a, b, span, written):
        if any(s <= span[0] < e or s < span[1] <= e for s, e in used):
            return
        used.append(span)
        if a and b and a <= b:
            out.append((a, b, written))

    def mk(y, m, d):
        try:
            return date(y, m, d) if y else None
        except ValueError:
            return None

    for m in BETWEEN.finditer(q):
        y2 = int(m.group(6)) if m.group(6) else only
        y1 = int(m.group(3)) if m.group(3) else y2
        add(mk(y1, _month(m.group(2)), int(m.group(1))), mk(y2, _month(m.group(5)), int(m.group(4))), m.span(),
            m.group(0))
    for m in ISO.finditer(q):
        d = mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        add(d, d, m.span(), m.group(0))
    for m in DAY_MON.finditer(q):
        y = int(m.group(4)) if m.group(4) else only
        mo = _month(m.group(3))
        a = mk(y, mo, int(m.group(1)))
        b = mk(y, mo, int(m.group(2))) if m.group(2) else a
        if b and a and b < a:  # "12-13 April" across midnight is fine; "30-1 May" is the next month: leave it out
            continue
        add(a, b, m.span(), m.group(0))
    for m in MON_DAY.finditer(q):
        y = int(m.group(4)) if m.group(4) else only
        mo = _month(m.group(1))
        a = mk(y, mo, int(m.group(2)))
        b = mk(y, mo, int(m.group(3))) if m.group(3) else a
        add(a, b, m.span(), m.group(0))
    for m in MON_YEAR.finditer(q):
        y, mo = int(m.group(2)), _month(m.group(1))
        add(date(y, mo, 1), date(y, mo, calendar.monthrange(y, mo)[1]), m.span(), m.group(0))
    return out


def windows(conn, case_id, question: str) -> dict[str, Any]:
    """The question's dates as windows in the case's time zone: ``{"zone", "windows": [{"from", "to", "written"}],
    "notes"}``. ``from``/``to`` are UTC instants (local midnight to the next local midnight)."""
    spans = date_spans(question)
    zone_name, basis = "UTC", "utc_default"
    notes: list[str] = []
    if spans and conn is not None:
        try:
            from services.phone import streams
            z = streams.case_zone(conn, str(case_id))
            zone_name, basis = z["name"], z["basis"]
            if z.get("note"):
                notes.append(z["note"])
        except Exception:  # noqa: BLE001 - a case without phone views: UTC, said so
            notes.append("The case time zone could not be read; dates are read in UTC.")
    from services.phone import time_display as T
    tz = T.tz(zone_name) if zone_name else timezone.utc
    out = []
    for a, b, written in spans:
        start = datetime.combine(a, time(0), tz).astimezone(timezone.utc)
        end = datetime.combine(b + timedelta(days=1), time(0), tz).astimezone(timezone.utc)
        out.append({"from": start.isoformat(), "to": end.isoformat(), "written": written,
                    "days": "%s to %s" % (a.isoformat(), b.isoformat())})
    if re.search(r"\b\d{1,2}(?:st|nd|rd|th)?\s+" + _MON + r"\b", question or "", re.I) and not out:
        notes.append("A date in the question has no year (or several years are named), so it was not turned into a "
                     "window; write the year.")
    return {"zone": zone_name, "zone_basis": basis, "windows": out, "notes": notes}


INITIALS = re.compile(r"(?<![A-Za-z])((?:[A-Z]\.\s?){2,3})(?![A-Za-z])")


def initials(text_: str) -> str:
    """The letters of initials as written ("D.O." -> "do"), or "" when the text is not initials."""
    m = INITIALS.fullmatch((text_ or "").strip())
    return re.sub(r"[^A-Za-z]", "", m.group(1)).lower() if m else ""


def name_initials(name: str) -> str:
    """A name's initials ("Desmond Okafor" -> "do")."""
    return "".join(w[0] for w in re.findall(r"[^\W\d_]+", name or "")).lower()


def names(question: str) -> list[str]:
    """Capitalised words and runs of them that may be names (``Harold Vint``, ``Harold``, ``Vint``), the run first;
    initials as written (``D.O.``). Question words and calendar words split a run (``Did Harold Vint`` gives
    ``Harold Vint``). A short name a phone may save ("Dee") counts: three letters or more."""
    found: list[str] = [m.group(1).strip() for m in INITIALS.finditer(question or "")]
    for m in NAME.finditer(question or ""):
        run: list[str] = []
        for w in m.group(1).split() + [None]:
            if w is not None and w not in NOT_NAMES:
                run.append(w)
                continue
            if run:
                for c in ([" ".join(run[:3])] if len(run) > 1 else []) + run:
                    if c not in found:
                        found.append(c)
            run = []
    return found


def expansions(conn, case_id, question: str) -> list[dict[str, Any]]:
    """Each name in the question tied to what the case holds for it: ``{"name", "term", "kind", "basis"}``. ``term``
    is searched beside the question's words. Phone contact names are what a phone's address book or messages call the
    identity; account holders are what a statement prints."""
    if conn is None:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(name, term, kind, basis):
        t = (term or "").strip()
        if not t or t.casefold() in seen or len(out) >= MAX_EXPANSIONS:
            return
        seen.add(t.casefold())
        out.append({"name": name, "term": t, "kind": kind, "basis": basis})

    for name in names(question):
        like = "%" + name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        try:
            with conn.begin_nested():
                rows = conn.execute(text(
                "SELECT DISTINCT n.name, i.value_display, i.kind, i.person_id IS NOT NULL AS linked FROM pv_identity_name n "
                "JOIN pv_identity i ON i.identity_id = n.identity_id AND i.case_id = n.case_id WHERE n.case_id = :c AND "
                "n.name ILIKE :p ORDER BY 1, 2 LIMIT 20"), {"c": str(case_id), "p": like}).fetchall()
        except Exception:  # noqa: BLE001 - a case without phone views (the savepoint is rolled back, nothing else)
            rows = []
        for r in rows:
            basis = ("a phone's contact name %r, linked to a person in the case" if r.linked
                     else "a phone's contact name %r (suggested, not confirmed by a person)") % r.name
            add(name, r.value_display, r.kind or "identity", basis)
            if r.name and r.name.casefold() != name.casefold():
                add(name, r.name, "contact_name", "another name a phone gives the same identity (%s)" % (
                    r.value_display or "no number"))
        # the other names the phones save for the same identity ("Dee" on one phone is "Desmond Okafor" on another),
        # and the person a person linked it to
        try:
            with conn.begin_nested():
                others = conn.execute(text(
                    "SELECT DISTINCT o.name, i.value_display, p.display_name FROM pv_identity_name n JOIN pv_identity i "
                    "ON i.identity_id = n.identity_id AND i.case_id = n.case_id JOIN pv_identity j ON j.case_id = "
                    "i.case_id AND j.identity_key = i.identity_key JOIN pv_identity_name o ON o.identity_id = "
                    "j.identity_id AND o.case_id = j.case_id LEFT JOIN case_profiles p ON p.id = i.person_id AND "
                    "p.archived_at IS NULL WHERE n.case_id = :c AND n.name ILIKE :p ORDER BY 1 LIMIT 20"),
                    {"c": str(case_id), "p": like}).fetchall()
        except Exception:  # noqa: BLE001 - a case without phone views
            others = []
        for o in others:
            if o.display_name and o.display_name.casefold() != name.casefold():
                add(name, o.display_name, "person", "the person a person linked the identity %s to" % (
                    o.value_display or ""))
            if o.name and o.name.casefold() != name.casefold():
                add(name, o.name, "contact_name", "another name a phone saves for the identity %s (suggested, not "
                    "confirmed by a person)" % (o.value_display or "no number"))
        try:
            with conn.begin_nested():
                accts = conn.execute(text(
                    "SELECT DISTINCT holder_name, identifier_as_printed FROM financial_accounts WHERE case_id = :c AND "
                    "holder_name ILIKE :p AND identifier_as_printed IS NOT NULL LIMIT 10"),
                    {"c": str(case_id), "p": like}).fetchall()
        except Exception:  # noqa: BLE001
            accts = []
        for a in accts:
            add(name, a.identifier_as_printed, "account", "the account a statement prints as held by %s" % a.holder_name)
    return out


# phones searched as one person's own: a name such as "Ruiz" may own several
MAX_OWN_PHONES = 4


def _same_person(asked: str, owner_name: str) -> bool:
    """Whether a name as asked ("Lena Marsh", "Lena") is the owner's name: every word asked is a word of it."""
    want = asked.casefold().split()
    have = set(re.findall(r"[\w'.-]+", owner_name.casefold()))
    return bool(want) and all(w in have for w in want)


def own_phones(conn, case_id, question: str) -> list[dict[str, Any]]:
    """The phones a name in the question owns: ``{"name", "extraction_id", "label", "basis"}``, longest name first.

    A phone is a person's own when its owner (a person's decision, else the computed owner number) is a number a
    phone saves under that name or a person in the case linked to it, or, with no decision recorded, when the name
    its own records give the owner most often is that name ("Owner of Phone 6: Lena Marsh"). A message on that phone
    is about its owner without naming her ("You received $500.00 from Travis K.", demo case, 17 Nov), so the case
    search gives these phones a list of their own (``net._own_phone_list``)."""
    if conn is None:
        return []
    asked = [n for n in names(question) if " " in n] or names(question)
    if not asked:
        return []
    from services.phone import identities
    from services.phone.readings import phone_labels
    try:
        with conn.begin_nested():
            phones = [str(r[0]) for r in conn.execute(text(
                "SELECT extraction_id FROM pv_extraction WHERE case_id = :c AND standing = 'active' ORDER BY "
                "created_at, extraction_id"), {"c": str(case_id)})]
            labels = phone_labels(conn, case_id) if phones else {}
            out: list[dict[str, Any]] = []
            for ext in phones:
                own = identities.owner(conn, ext)
                keys = own.get("owner_identity_keys") or []
                owner_names: list[tuple[str, str]] = []
                if keys:
                    for r in conn.execute(text(
                            "SELECT DISTINCT n.name, p.display_name FROM pv_identity i LEFT JOIN pv_identity_name n ON "
                            "n.identity_id = i.identity_id AND n.case_id = i.case_id LEFT JOIN case_profiles p ON "
                            "p.id = i.person_id AND p.archived_at IS NULL WHERE i.case_id = :c AND i.identity_key = "
                            "ANY(:k)"), {"c": str(case_id), "k": list(keys)}):
                        if r.display_name:
                            owner_names.append((r.display_name, "a person in the case linked to its owner's number"))
                        if r.name:
                            owner_names.append((r.name, "a phone saves its owner's number as %r" % r.name))
                if not own.get("decided"):
                    named = sorted((c for c in own.get("candidates") or [] if c["candidate_kind"] == "name"
                                    and c.get("name")), key=lambda c: (-(c.get("occurrences") or 0), c["name"]))
                    if named:
                        owner_names.append((named[0]["name"], "its own records name its owner %r" % named[0]["name"]))
                for name in asked:
                    hit = next((b for n, b in owner_names if _same_person(name, n)), None)
                    if hit:
                        out.append({"name": name, "extraction_id": ext, "label": labels.get(ext) or "Phone",
                                    "basis": hit})
                        break
    except Exception:  # noqa: BLE001 - a case without phone views (the savepoint is rolled back, nothing else)
        logger.warning("Own phone lookup failed", exc_info=True)
        return []
    out.sort(key=lambda o: -len(o["name"]))
    return out[:MAX_OWN_PHONES]


def understand(conn, case_id, question: str) -> dict[str, Any]:
    from services.phone import chat_retrieval
    w = windows(conn, case_id, question)
    return {"terms": chat_retrieval.terms(question), "names": names(question),
            "expansions": expansions(conn, case_id, question), "own_phones": own_phones(conn, case_id, question),
            "windows": w["windows"], "zone": w["zone"], "notes": w["notes"], "phrasings": []}
