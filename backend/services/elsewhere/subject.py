"""What is being checked: one phone record, or a statement (people, period, places, amounts, check numbers).

``from_record`` reads the record's people, time and text from the phone tables (current generation, active
phones only); ``from_statement`` takes what the caller says and reads the cited records the same way. Amounts come
from the phone money parser (``services.phone_analysis.money_parse``), check numbers and account endings from
``words``; nothing here calls a model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import text

from services.elsewhere import words as W

MAX_RECORDS = 20
MAX_TERMS = 12


class NotFound(LookupError):
    pass


class BadSubject(ValueError):
    pass


@dataclass
class Person:
    name: str | None = None
    numbers: list = field(default_factory=list)   # number keys (last ten digits)
    emails: list = field(default_factory=list)
    shown: str | None = None                      # as the record shows it ("Nell (+1 717-555-0261)")

    def label(self):
        return self.name or self.shown or (self.numbers[0] if self.numbers else "this person")


@dataclass
class Record:
    record_uid: str
    extraction_id: str
    kind: str | None
    model_type: str
    instant: datetime | None
    body: str
    deleted_state: str | None
    people: list                                  # [Person]
    owner_key: str | None = None                  # number key of the phone's owner, when the record has one


@dataclass
class Subject:
    kind: str                                     # record | statement
    case_id: str
    text: str = ""
    people: list = field(default_factory=list)
    start: date | None = None
    end: date | None = None
    anchor: datetime | None = None
    amounts: list = field(default_factory=list)   # [(minor, currency)]
    references: list = field(default_factory=list)
    accounts: list = field(default_factory=list)  # account endings or numbers (digits)
    places: list = field(default_factory=list)    # [{"name", "lat", "lon", "radius_m"}]
    terms: list = field(default_factory=list)     # names of firms and places read from the text
    records: list = field(default_factory=list)   # [Record]
    phone_scope: list | None = None               # extraction ids the screen has on; None is every phone

    def as_dict(self):
        return {"kind": self.kind,
                "people": [{"name": p.name, "shown": p.shown, "numbers": p.numbers, "emails": p.emails}
                           for p in self.people],
                "period": {"start": self.start.isoformat() if self.start else None,
                           "end": self.end.isoformat() if self.end else None},
                "amounts": [{"minor": m, "currency": c, "text": W.money_text(m, c)} for m, c in self.amounts],
                "references": self.references, "accounts": self.accounts, "places": self.places,
                "terms": self.terms, "record_uids": [r.record_uid for r in self.records]}

    def names(self, strong_only=False):
        out = []
        for p in self.people:
            if p.name and (not strong_only or W.strong_name(p.name)):
                out.append(p.name)
        return list(dict.fromkeys(out))

    def number_keys(self):
        return list(dict.fromkeys(n for p in self.people for n in p.numbers))


def _record_row(conn, case_id, record_uid):
    return conn.execute(text(
        "SELECT s.record_uid::text AS uid, s.extraction_id::text AS ext, s.model_type, s.first_instant, "
        "s.deleted_state, s.root_record_uid::text AS root, c.kind, c.body, c.subject, c.sort_instant "
        "FROM phone_record_summaries s JOIN phone_interpretation_state st ON st.extraction_id = s.extraction_id AND "
        "st.generation = s.generation JOIN phone_extractions e ON e.id = s.extraction_id AND e.standing = 'active' "
        "LEFT JOIN pv_comm_event c ON c.record_uid = s.record_uid "
        "WHERE s.record_uid = CAST(:u AS uuid) AND s.case_id = CAST(:c AS uuid)"),
        {"u": str(record_uid), "c": str(case_id)}).first()


def _record_text(conn, record_uid):
    rows = conn.execute(text(
        "SELECT value FROM pv_text WHERE record_uid = CAST(:u AS uuid) AND NOT is_sensitive"), {"u": str(record_uid)})
    return " ".join(r[0] for r in rows if r[0])


def _people(conn, ext, record_uid, root):
    rows = conn.execute(text(
        "SELECT record_uid::text AS uid, identifier_raw, name_in_record, is_phone_owner, identity_kind FROM "
        "phone_participations p JOIN phone_interpretation_state st ON st.extraction_id = p.extraction_id AND "
        "st.generation = p.generation WHERE p.extraction_id = CAST(:e AS uuid) AND (p.record_uid = CAST(:u AS uuid) "
        "OR p.record_uid = CAST(:r AS uuid))"), {"e": ext, "u": record_uid, "r": root}).fetchall()
    own = [r for r in rows if r.uid == record_uid] or rows   # the record's own parties, else its conversation's
    people, owner = {}, None
    for r in own:
        key, email = W.identifier_key(r.identifier_raw)
        ident = key or email or W.fold(r.name_in_record)
        if not ident:
            continue
        p = people.setdefault(ident, Person())
        if r.name_in_record and not p.name:
            p.name = r.name_in_record
        if key and key not in p.numbers:
            p.numbers.append(key)
        if email and email not in p.emails:
            p.emails.append(email)
        if r.identifier_raw:
            # a chat address that is a number is shown as the number
            shown = r.identifier_raw if email or "@" not in r.identifier_raw else \
                "+" + W.digits(r.identifier_raw.split("@", 1)[0])
            p.shown = "%s (%s)" % (r.name_in_record, shown) if r.name_in_record else shown
        if r.is_phone_owner and key:
            owner = key
    return list(people.values()), owner


def load_record(conn, case_id, record_uid) -> Record:
    row = _record_row(conn, case_id, record_uid)
    if row is None:
        raise NotFound("This record is not in this case.")
    body = " ".join(x for x in (row.subject, row.body) if x) or _record_text(conn, row.uid)
    people, owner = _people(conn, row.ext, row.uid, row.root)
    return Record(record_uid=row.uid, extraction_id=row.ext, kind=row.kind, model_type=row.model_type,
                  instant=row.sort_instant or row.first_instant, body=body or "", deleted_state=row.deleted_state,
                  people=people, owner_key=owner)


def _read_text(subject, body):
    from services.phone_analysis import money_parse
    reading = money_parse.parse(body or "")
    if reading is not None and reading.amount_minor is not None:
        pair = (int(reading.amount_minor), reading.currency or "USD")
        if pair not in subject.amounts:
            subject.amounts.append(pair)
    for ref in W.references_in(body):
        if ref not in subject.references:
            subject.references.append(ref)
    for end in W.endings_in(body):
        if end not in subject.accounts:
            subject.accounts.append(end)
    people_words = {t for p in subject.people for t in W.name_tokens(p.name)}
    for phrase in W.name_phrases(body):
        toks = W.name_tokens(phrase)
        if toks and not set(toks) <= people_words and phrase not in subject.terms:
            subject.terms.append(phrase)
    del subject.terms[MAX_TERMS:]


def from_record(conn, case_id, record_uid) -> Subject:
    rec = load_record(conn, case_id, record_uid)
    s = Subject(kind="record", case_id=str(case_id), text=rec.body, people=list(rec.people), records=[rec],
                anchor=rec.instant)
    if rec.instant is not None:
        s.start = s.end = rec.instant.date()
    _read_text(s, rec.body)
    return s


def _date(v, what):
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise BadSubject("The %s date is not a date (use YYYY-MM-DD)." % what) from None


def _merge_person(people, p):
    """Add a cited record's party to the statement's people, joining it to the person it is: the same number, or a
    name whose words are all in one given name ("Dorian (office)" is the statement's "Dorian Pell")."""
    for q in people:
        same_number = bool(set(p.numbers) & set(q.numbers)) or bool(set(p.emails) & set(q.emails))
        toks, qtoks = set(W.name_tokens(p.name)), set(W.name_tokens(q.name))
        same_name = bool(toks) and bool(qtoks) and (toks <= qtoks or qtoks <= toks)
        if same_number or (same_name and not (q.numbers and p.numbers)):
            q.numbers += [n for n in p.numbers if n not in q.numbers]
            q.emails += [e for e in p.emails if e not in q.emails]
            if len(qtoks) < len(toks):
                q.name = p.name
            q.shown = q.shown or p.shown
            return
    people.append(p)


def _owner_numbers(conn, case_id, people):
    """A person given by full name only takes the number of the phone the report names them the owner of (its best
    owner number). Said in the person's shown text, so the link is never silent; a name two phones' owners share is
    left alone."""
    want = [p for p in people if not p.numbers and not p.emails and p.name and W.strong_name(p.name)]
    if not want:
        return
    owners = {}
    for r in conn.execute(text(
            "SELECT extraction_id::text AS ext, candidate_kind, identity_key, name, tier FROM pv_owner_candidate "
            "WHERE case_id = CAST(:c AS uuid) AND candidate_kind IN ('number', 'name') ORDER BY tier NULLS LAST"),
            {"c": str(case_id)}):
        o = owners.setdefault(r.ext, {"names": [], "number": None})
        if r.candidate_kind == "name" and r.name:
            o["names"].append(r.name)
        elif r.candidate_kind == "number" and o["number"] is None:
            o["number"] = W.number_key((r.identity_key or "").split(":", 1)[-1])
    for p in want:
        hits = [o for o in owners.values() if o["number"] and any(
            W.name_in(p.name, n) and W.name_in(n, p.name) for n in o["names"])]
        if len(hits) == 1:
            p.numbers.append(hits[0]["number"])
            p.shown = "%s (the owner of a phone in this case, by the report)" % p.name


def from_statement(conn, case_id, payload: dict) -> Subject:
    payload = payload or {}
    s = Subject(kind="statement", case_id=str(case_id), text=str(payload.get("text") or "")[:4000])
    for p in (payload.get("people") or [])[:20]:
        person = Person(name=(p.get("name") or None),
                        numbers=[k for k in (W.number_key(n) for n in p.get("numbers") or []) if k],
                        emails=[str(e).lower() for e in p.get("emails") or [] if "@" in str(e)])
        if person.name or person.numbers or person.emails:
            s.people.append(person)
    period = payload.get("period") or {}
    s.start, s.end = _date(period.get("start"), "start"), _date(period.get("end"), "end")
    if s.start and s.end and s.end < s.start:
        raise BadSubject("The period ends before it starts.")
    for a in (payload.get("amounts") or [])[:20]:
        try:
            s.amounts.append((int(a["minor"]), str(a.get("currency") or "USD").upper()[:3]))
        except (KeyError, TypeError, ValueError):
            raise BadSubject("Each amount needs a whole number of cents in 'minor'.") from None
    s.references = [str(r).strip() for r in (payload.get("references") or []) if str(r).strip()][:20]
    s.accounts = [W.digits(a) for a in (payload.get("accounts") or []) if len(W.digits(a)) >= 4][:10]
    for pl in (payload.get("places") or [])[:10]:
        place = {"name": pl.get("name") or None, "lat": pl.get("lat"), "lon": pl.get("lon"),
                 "radius_m": float(pl.get("radius_m") or 500)}
        if place["name"] or (place["lat"] is not None and place["lon"] is not None):
            s.places.append(place)
    for t in (payload.get("words") or [])[:MAX_TERMS]:
        if str(t).strip() and str(t).strip() not in s.terms:
            s.terms.append(str(t).strip()[:120])
    if payload.get("phones"):
        s.phone_scope = [str(e) for e in payload["phones"]][:50]
    uids = list(dict.fromkeys(str(u) for u in (payload.get("record_uids") or [])))
    if len(uids) > MAX_RECORDS:
        raise BadSubject("At most %d records can be checked at once; %d were given." % (MAX_RECORDS, len(uids)))
    for uid in uids:
        rec = load_record(conn, case_id, uid)
        s.records.append(rec)
        for p in rec.people:
            _merge_person(s.people, p)
        if rec.instant and not (period.get("start") or period.get("end")):
            d = rec.instant.date()
            s.start = min(s.start, d) if s.start else d
            s.end = max(s.end, d) if s.end else d
    _owner_numbers(conn, case_id, s.people)
    _read_text(s, s.text)
    for place in s.places:
        if place["name"] and place["name"] not in s.terms:
            s.terms.append(place["name"])
    if s.anchor is None and s.records and s.records[0].instant:
        s.anchor = s.records[0].instant
    if not (s.people or s.amounts or s.references or s.accounts or s.places or s.terms or s.records
            or s.start or s.end):
        raise BadSubject("Say what to check: people, a period, places, amounts, check numbers or records.")
    return s


def window(subject, before_days, after_days):
    """The dates searched around the subject; ``(None, None)`` when it has no date."""
    if subject.start is None and subject.end is None:
        return None, None
    return (subject.start or subject.end) - timedelta(days=before_days), \
        (subject.end or subject.start) + timedelta(days=after_days)
