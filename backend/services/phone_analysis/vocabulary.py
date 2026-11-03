"""The case vocabulary (05 section 10.3 step 1) and matching typed or searched text against it (step 2).

Terms and their kinds:

- ``contact_name``: tokens of the names the phones hold for each identity (02, ``pv_identity_name``);
- ``phone_number``: the digits of each identity's number (02, ``pv_identity.value_normalised``, 7 digits or more);
- ``account_ending``: the last four digits of each account identifier in the case's financial records;
- ``financial_name``: tokens of account holders and of counterparties on the effective ledger rows (the corrected
  value is the one read: ``money_signals._ledger``).

Not included yet, and stated on every result and measurement that uses the vocabulary (``NOT_INCLUDED``): Loupe's
case entities (their names live in the graph), ledger amounts in the phone's locale forms, addresses and place
names, and terms an investigator adds. Leaving them out can only lower the counts.

Matching (10.3 step 2), decided in 19.S10-a: the 03 search fold, then word tokens (letters and digits) of at least
4 characters, not all digits, equal to a name term; a run of digits equal to an account ending or ending with one
(a full account number typed); a run of at least 7 digits that an identity's number ends with, or that ends with an
identity's number (with or without the country code). A 4 to 6 digit run is never a phone-number hit: on C3 any 4
digits in a web address matched some number (3,523 distinct matches in 5,866 addresses). Values never leave this
module; callers get kinds, counts and record ids.
"""
from __future__ import annotations

import re

from sqlalchemy import text

from services.phone.fold import fold

MIN_TOKEN = 4
MIN_PHONE_RUN = 7
_WORD = re.compile(r"\w+")
_DIGITS = re.compile(r"\d{4,}")
KINDS = ("contact_name", "phone_number", "account_ending", "financial_name")
KIND_WORDS = {"contact_name": "a name the phones hold for a contact",
              "phone_number": "a phone number in the case",
              "account_ending": "an account ending in the financial records",
              "financial_name": "an account holder or counterparty in the financial records"}
NOT_INCLUDED = ("Loupe case entities", "ledger amounts", "addresses and place names", "investigator-added terms")


def name_tokens(value) -> set:
    return {t for t in _WORD.findall(fold(value or "")) if len(t) >= MIN_TOKEN and not t.isdigit()}


def build(conn, case_id, ledger=True) -> dict:
    """``{"names": {token: {kind}}, "numbers": {digits}, "endings": {4 digits}}`` for the case."""
    names: dict = {}

    def add(value, kind):
        for t in name_tokens(value):
            names.setdefault(t, set()).add(kind)
    for (name,) in conn.execute(text("SELECT DISTINCT name FROM pv_identity_name WHERE case_id = :c"),
                                {"c": str(case_id)}):
        add(name, "contact_name")
    numbers = set()
    for (v,) in conn.execute(text("SELECT DISTINCT value_normalised FROM pv_identity WHERE case_id = :c AND "
                                  "value_normalised ~ '[0-9]{7,}'"), {"c": str(case_id)}):
        d = re.sub(r"\D", "", v or "")
        if len(d) >= MIN_PHONE_RUN:
            numbers.add(d)
    endings = set()
    if ledger:
        from services.phone_analysis.money_signals import _ledger
        accounts, entries, _ = _ledger(conn, case_id)
        for a in accounts.values():
            for ident in a["identifiers"]:
                d = re.sub(r"\D", "", ident or "")
                if len(d) >= 4:
                    endings.add(d[-4:])
            add(a["holder"], "financial_name")
        for rows in entries.values():
            for e in rows:
                add(e["counterparty"], "financial_name")
    return {"names": names, "numbers": numbers, "endings": endings}


def _phone_hit(run, numbers) -> bool:
    return len(run) >= MIN_PHONE_RUN and any(n.endswith(run) or run.endswith(n) for n in numbers)


def matches(value, vocab) -> list:
    """``[(kind, token)]`` for every distinct vocabulary term the value matches (the token is the matched text of
    the value, for the elsewhere search; it never leaves the backend)."""
    out = []
    for t in sorted(set(_WORD.findall(fold(value or "")))):
        for kind in sorted(vocab["names"].get(t, ())):
            out.append((kind, t))
    for run in sorted(set(_DIGITS.findall(value or ""))):
        if any(run.endswith(e) for e in vocab["endings"]):
            out.append(("account_ending", run))
        if _phone_hit(run, vocab["numbers"]):
            out.append(("phone_number", run))
    return out


def hit(value, vocab) -> str | None:
    """The first matched kind, or None."""
    m = matches(value, vocab)
    return m[0][0] if m else None


def tokens_of(value, vocab) -> list:
    """The distinct matched tokens of a value."""
    return sorted({t for _, t in matches(value, vocab)})


ELSEWHERE_TYPES = ("InstantMessage", "Email", "Note", "SearchedItem", "CalendarEntry", "ReplyMessageData")


def elsewhere(conn, extraction_id, token, limit=20) -> tuple:
    """``(count, [record_uid...])``: the phone's own messages, emails, notes, searches and calendar entries (10.3
    step 3) whose non-sensitive text holds the token; at most ``limit`` record ids, the count is the full count."""
    p = {"e": str(extraction_id), "t": list(ELSEWHERE_TYPES),
         "p": "%" + token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"}
    where = ("extraction_id = :e AND model_type = ANY(:t) AND NOT coalesce(is_sensitive, false) AND value_folded "
             "LIKE :p")
    n = int(conn.execute(text("SELECT count(DISTINCT record_uid) FROM pv_text WHERE " + where), p).scalar() or 0)
    if not n:
        return 0, []
    uids = [str(r[0]) for r in conn.execute(text(
        "SELECT DISTINCT record_uid FROM pv_text WHERE " + where + " ORDER BY record_uid LIMIT %d" % int(limit)), p)]
    return n, uids
