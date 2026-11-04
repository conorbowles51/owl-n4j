"""The case vocabulary (05 section 10.3 step 1) and matching typed or searched text against it (step 2).

Terms and their kinds:

- ``contact_name``: tokens of the names the phones hold for each identity (02, ``pv_identity_name``);
- ``phone_number``: the digits of each identity's number (02, ``pv_identity.value_normalised``, 7 digits or more);
- ``account_ending``: the last four digits of each account identifier in the case's financial records;
- ``financial_name``: tokens of account holders and of counterparties on the effective ledger rows (the corrected
  value is the one read: ``money_signals._ledger``).

- ``investigator_term``: the terms an investigator adds (10.3 step 1, 12.3 step 1): the case's case terms
  (Workspace notes tagged ``case term``) and the terms of its saved keyword lists
  (``services.search.keyword_lists.investigator_terms``).
- ``case_entity``: tokens of the names and aliases of the case's Loupe graph entities (people, organisations and the
  other named entity types of ``ENTITY_LABELS``), read with one bounded, case-scoped graph query per build
  (``_read_graph``). Only active nodes are read (not in the recycle bin, not system nodes), so a renamed entity
  contributes its current name and a merged one the name of the entity it was merged into (19.S10-d).
- ``ledger_amount``: the amounts of the effective ledger rows (``money_signals._ledger``, corrected value read),
  written in the phone's number forms (``amount_forms``, 19.S10-e) and matched as a whole number token (digits
  with their separators, not part of a longer number) of 4 or more digits. ``for_phone`` picks the forms of each phone's region.
- ``place``: addresses and place names from the case: the names and aliases of its graph location entities and the
  address fields of any graph entity (``location_formatted``, ``location_raw``, ``address``), each value whole and
  each comma-separated part of it, matched as a phrase (whole folded words in order), the way ``investigator_term``
  is. The financial records store no holder address (no address column or metadata key on accounts, periods or
  rows), so there is none to read from them (19.S10-f).

``NOT_INCLUDED`` is empty: every kind of 10.3 step 1 is read. A build that could not read a source says so in its
own ``not_included`` (``not_included(vocab)``), stated on every result and measurement that uses it; leaving a
source out can only lower the counts.

Matching (10.3 step 2), decided in 19.S10-a: the 03 search fold, then word tokens (letters and digits) of at least
4 characters, not all digits, equal to a name term; a run of digits equal to an account ending or ending with one
(a full account number typed); a run of at least 7 digits that an identity's number ends with, or that ends with an
identity's number (with or without the country code). A 4 to 6 digit run is never a phone-number hit: on C3 any 4
digits in a web address matched some number (3,523 distinct matches in 5,866 addresses). An investigator term (19.S10-c) matches
when its folded words occur in the folded value as whole words, in order (``cash drop`` matches "Cash-drop at 5" but
``cash`` does not match "cashew"), so a phrase is matched as one term; a term under 3 letters is not used. Values never leave this
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
KINDS = ("contact_name", "phone_number", "account_ending", "financial_name", "investigator_term", "case_entity",
         "ledger_amount", "place")
KIND_WORDS = {"contact_name": "a name the phones hold for a contact",
              "phone_number": "a phone number in the case",
              "account_ending": "an account ending in the financial records",
              "financial_name": "an account holder or counterparty in the financial records",
              "investigator_term": "a term an investigator added to the case",
              "case_entity": "a name or alias of a person, organisation or other entity in the case",
              "ledger_amount": "an amount in the case's ledger",
              "place": "an address or place name in the case"}
NOT_INCLUDED: tuple = ()
MIN_TERM = 3
# 19.S10-d: the named entity types of the case graph. Not read: the phone and financial projections (their names
# are already the 02 identities and the financial records), documents, and the types whose name is a title of a
# happening rather than the name of a thing (communications, events, transactions, legal actions, media,
# intelligence). Location types are read as places.
PLACE_LABELS = ("Location", "location")
ENTITY_LABELS = ("Person", "Organization", "Company", "Bank", "Group", "Vehicle", "Device", "DigitalAccount",
                 "CyberIdentity", "Account", "PhoneNumber", "NetworkIdentifier", "Drug", "Weapon",
                 "FinancialInstrument", "PhysicalEvidence", "Other") + PLACE_LABELS
GRAPH_LIMIT = 50000
GRAPH_TIMEOUT_S = 10
MIN_PLACE_LETTERS = 4
_AMOUNT = re.compile(r"(?<![\d.,])\d(?:[\d.,]*\d)?(?!\d)")


def name_tokens(value) -> set:
    return {t for t in _WORD.findall(fold(value or "")) if len(t) >= MIN_TOKEN and not t.isdigit()}


def build(conn, case_id, ledger=True, graph=True) -> dict:
    """``{"names": {token: {kind}}, "numbers": {digits}, "endings": {4 digits}, "terms": [phrase], "places":
    {first word: [phrase words]}, "amounts": {convention: {form}}, "amount_forms": {form}, "not_included": [...]}``
    for the case. ``amount_forms`` is every convention's forms until ``for_phone`` picks one phone's."""
    names: dict = {}
    missing: list = []

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
    amounts = {"dot": set(), "comma": set()}
    currencies = set()
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
                for conv, forms in amount_forms(e["amount_minor"], e["currency"]).items():
                    amounts[conv] |= forms
                if e["currency"]:
                    currencies.add(e["currency"].upper())
    places: dict = {}
    if graph:
        rows, note = _read_graph(str(case_id))
        if note:
            missing.append(note)
        for label, name, aliases, place_values in rows:
            aliases = [aliases] if isinstance(aliases, str) else (aliases or [])
            values = [v for v in [name] + list(aliases) if isinstance(v, str)]
            if label in PLACE_LABELS:
                for v in values:
                    _add_place(places, v)
            else:
                for v in values:
                    add(v, "case_entity")
            for v in place_values or []:
                _add_place(places, v)
    return {"names": names, "numbers": numbers, "endings": endings, "terms": investigator_terms(conn, case_id),
            "places": places, "amounts": amounts, "amount_forms": amounts["dot"] | amounts["comma"],
            "currencies": sorted(currencies), "not_included": missing}


def not_included(vocab) -> list:
    """What this build of the vocabulary could not read (empty when every source was read)."""
    return list(NOT_INCLUDED) + list(vocab.get("not_included") or [])


def vocabulary_partial_detail(vocab) -> str | None:
    """The sentence a result states when the vocabulary was partial, or None when nothing is left out."""
    missing = not_included(vocab)
    return ("The comparison does not include: %s." % ", ".join(missing)) if missing else None


# ---- case entities and places (the graph) ------------------------------------------------------------------------

def _graph_query() -> str:
    parts = ["MATCH (n:`%s` {case_id: $case_id}) RETURN n" % label for label in ENTITY_LABELS]
    return ("CALL {\n" + "\nUNION ALL\n".join(parts) + "\n}\nWITH n WHERE coalesce(n.system_node, false) <> true AND "
            "NONE(l IN labels(n) WHERE l IN ['RecycleBin', 'RecycleBinItem'])\nWITH n LIMIT $limit\nRETURN "
            "collect([[l IN labels(n) WHERE l IN $labels][0], n.name, n.aliases, [x IN [n.location_formatted, "
            "n.location_raw, n.address] WHERE x IS NOT NULL]]) AS rows")


def _graph_rows(case_id) -> list:
    """The one bounded read of the case graph: ``[[label, name, aliases, [address values]]]``, at most
    ``GRAPH_LIMIT + 1`` rows (the extra row tells a cut list from a whole one)."""
    from services.neo4j.driver import driver
    rows, _ = driver.run_cypher_read_bounded(
        _graph_query(), {"case_id": case_id, "limit": GRAPH_LIMIT + 1, "labels": list(ENTITY_LABELS)},
        max_rows=1, timeout_seconds=GRAPH_TIMEOUT_S)
    return (rows[0].get("rows") if rows else None) or []


GRAPH_UNREADABLE_NOTE = "Loupe case entities and the case's places (the case graph could not be read)"
# an input revision of an unreadable graph starts with this, so the run's input check can name the graph as the cause
GRAPH_UNREADABLE_PREFIX = "unreadable:"


def _read_graph(case_id) -> tuple:
    """``(rows, note)``: the case's graph entities, or none and the reason when the graph could not be read; a list
    cut at ``GRAPH_LIMIT`` keeps the first rows and says so."""
    import logging
    try:
        rows = _graph_rows(case_id)
    except Exception as exc:  # noqa: BLE001 - an unreadable graph leaves its kinds out, stated on every result
        logging.getLogger(__name__).warning("case graph not read for the vocabulary: %s", type(exc).__name__)
        return [], GRAPH_UNREADABLE_NOTE
    if len(rows) > GRAPH_LIMIT:
        return rows[:GRAPH_LIMIT], ("Loupe case entities and places beyond the first %d graph entities"
                                    % GRAPH_LIMIT)
    return rows, None


def graph_revision(case_id) -> str:
    """What the case graph gave the vocabulary, for the input manifest: a new, renamed or merged entity makes a new
    run."""
    import hashlib
    import json
    rows, note = _read_graph(str(case_id))
    digest = hashlib.sha256(json.dumps([sorted(json.dumps(r, sort_keys=True, default=str) for r in rows), note])
                            .encode()).hexdigest()
    return GRAPH_UNREADABLE_PREFIX + digest if note == GRAPH_UNREADABLE_NOTE else digest


def _place_words(value) -> list:
    words = fold(value or "").split()
    return words if sum(len(w) for w in words if not w.isdigit()) >= MIN_PLACE_LETTERS else []


def _add_place(places, value):
    """A place value whole and each comma-separated part of it, as folded phrases indexed by their first word."""
    if not isinstance(value, str):
        return
    for part in [value] + (value.split(",") if "," in value else []):
        words = _place_words(part)
        if words:
            bucket = places.setdefault(words[0], [])
            if words not in bucket:
                bucket.append(words)


def _place_hits(folded, places) -> list:
    words = folded.split()
    out = set()
    for i, w in enumerate(words):
        for phrase in places.get(w, ()):
            if words[i:i + len(phrase)] == phrase:
                out.add(" ".join(phrase))
    return sorted(out)


# ---- ledger amounts in the phone's number forms (19.S10-e) -------------------------------------------------------

# Countries whose numbers write the decimal with a comma and group thousands with a full stop (CLDR, the regions
# the case material comes from and their neighbours). Every other known region writes 1,234.56.
COMMA_DECIMAL_REGIONS = frozenset((
    "AR", "AT", "BA", "BE", "BO", "BR", "CL", "CO", "CR", "CY", "CZ", "DE", "DK", "EC", "EE", "ES", "FI", "FR", "GR",
    "HR", "HU", "ID", "IS", "IT", "LT", "LU", "LV", "MD", "ME", "MK", "NL", "NO", "PL", "PT", "PY", "RO", "RS", "RU",
    "SE", "SI", "SK", "TR", "UA", "UY", "VE", "VN"))
# A currency spoken in both conventions (the euro: Ireland and Malta write 1,234.56) leaves the phone with both.
BOTH_CONVENTION_CURRENCIES = frozenset(("EUR", "CHF"))
COMMA_CURRENCIES = frozenset(("BRL", "ARS", "CLP", "COP", "UYU", "PYG", "VES", "DKK", "NOK", "SEK", "PLN", "CZK",
                              "HUF", "RON", "RUB", "TRY", "UAH", "IDR", "VND", "ISK", "RSD"))
CURRENCY_EXPONENT = {"JPY": 0, "KRW": 0, "CLP": 0, "ISK": 0, "VND": 0, "PYG": 0, "HUF": 2, "IDR": 2, "KWD": 3,
                     "BHD": 3, "OMR": 3, "JOD": 3, "TND": 3}


def _group(n: int, sep: str) -> str:
    return "{:,}".format(n).replace(",", sep)


def amount_forms(amount_minor, currency) -> dict:
    """``{"dot": {...}, "comma": {...}}``: an amount written as people write it, each with at least 4 digits.
    Dot convention: ``1234.56`` and ``1,234.56``; comma convention: ``1234,56`` and ``1.234,56``. A whole amount
    also without its decimals when grouped (``1,234`` / ``1.234``); a currency without minor units only so. The
    plain whole form (``1234``) is not used (19.S10-e): measured against the C3 and C9 phones with an unrelated
    ledger of 27,673 rows it matched 112 records on C3 (109 page addresses and titles, 2 searches, 1 typed word;
    years and page numbers), where every decimal and grouped form matched none."""
    exp = CURRENCY_EXPONENT.get((currency or "").upper(), 2)
    m = abs(int(amount_minor))
    whole, frac = divmod(m, 10 ** exp) if exp else (m, 0)
    out = {"dot": set(), "comma": set()}
    if exp:
        f = str(frac).rjust(exp, "0")
        out["dot"] |= {"%d.%s" % (whole, f), "%s.%s" % (_group(whole, ","), f)}
        out["comma"] |= {"%d,%s" % (whole, f), "%s,%s" % (_group(whole, "."), f)}
    if frac == 0 and whole >= 1000:
        out["dot"].add(_group(whole, ","))
        out["comma"].add(_group(whole, "."))
    for conv in out:
        out[conv] = {x for x in out[conv] if sum(ch.isdigit() for ch in x) >= MIN_TOKEN}
    return out


def phone_convention(conn, extraction_id, currencies=()) -> tuple:
    """``(conventions, basis)`` for one phone: its region decision or the case's phone region, else the country of
    its owner's number (02), else the ledger's currencies; a phone with none of these keeps both conventions."""
    region, basis = None, None
    from services.phone.mappings import apply
    r, b = apply.default_region(conn, extraction_id)
    if b != "assumed_default":
        region, basis = r, b
    if region is None:
        import phonenumbers
        for (key,) in conn.execute(text(
                "SELECT identity_key FROM phone_owner_candidates WHERE extraction_id = :e AND identity_key LIKE "
                "'phone:+%' ORDER BY tier, identity_key"), {"e": str(extraction_id)}):
            try:
                region = phonenumbers.region_code_for_number(phonenumbers.parse(key[6:], None))
            except phonenumbers.NumberParseException:
                continue
            if region:
                basis = "owner_number"
                break
    if region:
        return (("comma",) if region.upper() in COMMA_DECIMAL_REGIONS else ("dot",)), "region %s (%s)" % (
            region.upper(), basis)
    convs = set()
    for c in currencies:
        if c in BOTH_CONVENTION_CURRENCIES:
            convs |= {"dot", "comma"}
        else:
            convs.add("comma" if c in COMMA_CURRENCIES else "dot")
    if convs:
        return tuple(sorted(convs)), "currency %s" % ", ".join(currencies)
    return ("comma", "dot"), "region and currency unknown"


def for_phone(conn, vocab, extraction_id) -> dict:
    """The vocabulary for one phone: its ledger amounts in that phone's number forms only."""
    convs, basis = phone_convention(conn, extraction_id, vocab.get("currencies") or ())
    forms = set()
    for c in convs:
        forms |= (vocab.get("amounts") or {}).get(c, set())
    return dict(vocab, amount_forms=forms, amount_conventions=convs, amount_basis=basis)


def investigator_terms(conn, case_id) -> list:
    """The case's investigator terms, folded, each at least 3 letters, distinct, in a stable order."""
    from services.search.keyword_lists import investigator_terms as read
    out = set()
    for t in read(conn, case_id):
        f = " ".join(fold(t).split())
        if len(f.replace(" ", "")) >= MIN_TERM:
            out.add(f)
    return sorted(out)


def terms_revision(conn, case_id) -> str:
    """What a run's investigator terms were, for the input manifest: a new or removed term makes a new run."""
    import hashlib
    return hashlib.sha256("\n".join(investigator_terms(conn, case_id)).encode()).hexdigest()


def _phone_hit(run, numbers) -> bool:
    return len(run) >= MIN_PHONE_RUN and any(n.endswith(run) or run.endswith(n) for n in numbers)


def matches(value, vocab) -> list:
    """``[(kind, token)]`` for every distinct vocabulary term the value matches (the token is the matched text of
    the value, for the elsewhere search; it never leaves the backend)."""
    out = []
    folded = fold(value or "")
    for t in sorted(set(_WORD.findall(folded))):
        for kind in sorted(vocab["names"].get(t, ())):
            out.append((kind, t))
    if vocab.get("terms"):
        padded = " %s " % " ".join(folded.split())
        for term in vocab["terms"]:
            if " %s " % term in padded:
                out.append(("investigator_term", term))
    if vocab.get("places"):
        for phrase in _place_hits(folded, vocab["places"]):
            out.append(("place", phrase))
    for run in sorted(set(_DIGITS.findall(value or ""))):
        if any(run.endswith(e) for e in vocab["endings"]):
            out.append(("account_ending", run))
        if _phone_hit(run, vocab["numbers"]):
            out.append(("phone_number", run))
    if vocab.get("amount_forms"):
        for tok in sorted(set(_AMOUNT.findall(value or ""))):
            if tok in vocab["amount_forms"]:
                out.append(("ledger_amount", fold(tok)))
    return out


def hit(value, vocab) -> str | None:
    """The first matched kind, or None."""
    m = matches(value, vocab)
    return m[0][0] if m else None


def tokens_of(value, vocab) -> list:
    """The distinct matched tokens of a value."""
    return sorted({t for _, t in matches(value, vocab)})


ELSEWHERE_TYPES = ("InstantMessage", "Email", "Note", "SearchedItem", "CalendarEntry", "ReplyMessageData")


def elsewhere(conn, extraction_id, token, limit=20, whole=False) -> tuple:
    """``(count, [record_uid...])``: the phone's own messages, emails, notes, searches and calendar entries (10.3
    step 3) whose non-sensitive text holds the token; at most ``limit`` record ids, the count is the full count.
    ``whole``: the token must stand as whole folded words (an amount, so "1 234 56" is not found inside
    "21 234 567")."""
    p = {"e": str(extraction_id), "t": list(ELSEWHERE_TYPES),
         "p": "%" + token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"}
    where = ("extraction_id = :e AND model_type = ANY(:t) AND NOT coalesce(is_sensitive, false) AND value_folded "
             "LIKE :p")
    if whole:
        p["w"] = "(^| )" + re.escape(token).replace("\\ ", " ") + "( |$)"
        where += " AND value_folded ~ :w"
    n = int(conn.execute(text("SELECT count(DISTINCT record_uid) FROM pv_text WHERE " + where), p).scalar() or 0)
    if not n:
        return 0, []
    uids = [str(r[0]) for r in conn.execute(text(
        "SELECT DISTINCT record_uid FROM pv_text WHERE " + where + " ORDER BY record_uid LIMIT %d" % int(limit)), p)]
    return n, uids
