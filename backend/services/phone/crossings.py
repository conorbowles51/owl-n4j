"""Crossings between the ledger, the Graph and the phones (docs/cellebrite/07 section 7.2: XF-1, XF-2, XF-8).

Every count here is the Conversations count for the scope the crossing opens: the stream filter is built the way
the Conversations page builds it from its URL (``frontend_v2/src/features/phones/lib/filter-url.ts``
``viewToFilter``: people, Involving, days in the case zone, copies once) and counted by the same index query, and the
URL that opens it is returned beside it. So the number on the button is the number the page shows.

- XF-1 ``payment_activity``: a ledger row's counterparty, through the reviewed identity path (the payment's reviewed
  counterparty, the party's reviewed entity links, the dossier on that entity, the phone identities linked to that
  dossier), and the phones' messages and calls with those people on the payment date and a day either side. The
  words are "1 day before", "same day", "1 day after"; a payment has a date and no time, so a time of day is never
  used. An unlinked payee says so and how to fix it.
- XF-2 ``person_activity``: a Graph person (its dossier) to its phone identities and their messages and calls.
- XF-8 ``counterparty_suggestions``: a phone contact's number or address equal to a reviewed account identifier of
  kind ``phone_number`` or ``email`` (02-U11) suggests that account's payments. Always "Suggested, not reviewed";
  nothing on the ledger changes.

In a case with no financial evidence the money crossings say "No financial records in this case. Add bank
statements to see payments beside the phones." and never show 0 payments (07 section 8).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sqlalchemy import text

from services.phone import money_presence

UNLINKED_PAYEE = "This payee is not linked to a person, so the phones cannot be matched. Link it in People."
NO_COUNTERPARTY = "This payment has no reviewed counterparty, so the phones cannot be matched. Review it first."
SUGGESTED = "Suggested, not reviewed"
DAY_WORDS = {-1: "1 day before", 0: "same day", 1: "1 day after"}
PAYMENTS_SHOWN = 50


class NotInCase(LookupError):
    pass


def _zone(conn, case_id) -> str:
    from services.phone import streams
    return streams.case_zone(conn, str(case_id))["name"]


def _day_bounds(d: date, zone: str) -> tuple[datetime, datetime]:
    """The Conversations page's day: local midnight to the next local midnight less a millisecond."""
    z = ZoneInfo(zone)
    start = datetime(d.year, d.month, d.day, tzinfo=z)
    nxt = d + timedelta(days=1)
    return start, datetime(nxt.year, nxt.month, nxt.day, tzinfo=z) - timedelta(milliseconds=1)


def conversations_scope(case_id, keys: list[str], from_day: date | None = None, to_day: date | None = None,
                        zone: str = "UTC") -> tuple[dict, str]:
    """``(stream filter, Conversations href)`` for Involving any of ``keys`` (one person's identities), optionally
    from one day to another in the case zone, as the page builds them from that URL."""
    f = {"case_id": str(case_id), "zone": {"mode": "case", "phone": None}, "participants": list(keys),
         "participant_mode": "any", "names": {"mode": "phone"}}
    q = {"tab": "people", "people": ",".join(keys)}
    if from_day:
        f["from_instant"] = _day_bounds(from_day, zone)[0].isoformat()
        q["from"] = from_day.isoformat()
    if to_day:
        f["to_instant"] = _day_bounds(to_day, zone)[1].isoformat()
        q["to"] = to_day.isoformat()
    return f, "/cases/%s/conversations?%s" % (case_id, urlencode(q))


def count(conn, f: dict) -> int:
    from services.phone import streams
    from services.phone.filters import StreamFilter
    return int(streams.index_comm_events(conn, StreamFilter.model_validate(f))["counts"].get("events") or 0)


def _dossier_keys(conn, case_id, dossier_ids) -> list[str]:
    if not dossier_ids:
        return []
    return sorted({r[0] for r in conn.execute(text(
        "SELECT identity_key FROM pv_identity WHERE case_id = :c AND person_id::text = ANY(:d)"),
        {"c": str(case_id), "d": [str(d) for d in dossier_ids]})})


def _dossiers_for_entities(conn, case_id, entity_keys) -> list[dict]:
    if not entity_keys:
        return []
    return [dict(r._mapping) for r in conn.execute(text(
        "SELECT id::text AS id, display_name AS name FROM case_profiles WHERE case_id = :c AND archived_at IS NULL "
        "AND canonical_entity_key = ANY(:k) ORDER BY display_name"), {"c": str(case_id), "k": list(entity_keys)})]


# ---- XF-1 ---------------------------------------------------------------------------------------------------------

def _counterparty_entities(session, case_id, link) -> set[str]:
    """The reviewed entity keys of a payment's counterparty: a party's own entity links, or an account's holders'."""
    from services.financial.account_identity import identity_state
    state = identity_state(session, case_id)
    if link["kind"] == "party":
        parties = {link["id"]}
    else:
        parties = set()
        for account in state["accounts"]:
            if account["id"] == link["id"]:
                parties = {r["party"]["id"] for r in account.get("relationships") or [] if r.get("role") == "holder"}
    keys = set()
    for account in state["accounts"]:
        for el in (account.get("identity_review") or {}).get("entity_links") or []:
            if el.get("party_id") in parties and el.get("entity_key"):
                keys.add(el["entity_key"])
    return keys


def payment_activity(session, case_id, transaction_id) -> dict:
    """XF-1: messages and calls with the payment's counterparty on the payment date and a day either side."""
    from postgres.models.financial import FinancialTransaction
    from services.financial.payment_counterparty_link import resolved_link, stored_link
    conn = session.connection()
    case_id = uuid.UUID(str(case_id))
    row = session.get(FinancialTransaction, uuid.UUID(str(transaction_id)))
    if row is None or row.case_id != case_id:
        raise NotInCase("That payment is not in this case.")
    d = row.ordering_date
    base = {"transaction_id": str(row.id), "payment_date": d.isoformat() if d else None,
            "date_basis": "the payment's date (a payment has a date and no time)"}
    phones = conn.execute(text("SELECT count(*) FROM pv_extraction WHERE case_id = :c AND standing = 'active'"),
                          {"c": str(case_id)}).scalar()
    if not phones:
        return {**base, "state": "no_phones", "sentence": "There are no phones in this case.", "days": []}
    link = resolved_link(session, case_id, stored_link((row.metadata_ or {}).get("investigation_labels"),
                                                       (row.provenance or {}).get("reviewed_counterparty")))
    if not link:
        return {**base, "state": "no_counterparty", "sentence": NO_COUNTERPARTY, "days": []}
    base["counterparty"] = {"kind": link["kind"], "id": link["id"], "label": link.get("label")}
    dossiers = _dossiers_for_entities(conn, case_id, _counterparty_entities(session, case_id, link))
    keys = _dossier_keys(conn, case_id, [x["id"] for x in dossiers])
    if not keys:
        return {**base, "state": "unlinked", "sentence": UNLINKED_PAYEE, "people": dossiers, "days": [],
                "people_href": "/cases/%s/dossiers" % case_id,
                "payee_dossier_offer": not dossiers}
    if d is None:
        return {**base, "state": "no_date", "sentence": "This payment has no date, so no day can be matched.",
                "people": dossiers, "days": []}
    zone = _zone(conn, case_id)
    days = []
    for offset in (-1, 0, 1):
        day = d + timedelta(days=offset)
        f, href = conversations_scope(case_id, keys, day, day, zone)
        days.append({"offset": offset, "words": DAY_WORDS[offset], "date": day.isoformat(), "count": count(conn, f),
                     "conversations_href": href})
    f, href = conversations_scope(case_id, keys, d - timedelta(days=1), d + timedelta(days=1), zone)
    total = count(conn, f)
    names = ", ".join(x["name"] for x in dossiers)
    return {**base, "state": "linked", "people": dossiers, "identity_keys": keys, "zone": zone, "days": days,
            "total": total, "conversations_href": href,
            "sentence": "%s message%s and call%s with %s from 1 day before to 1 day after the payment (days in %s)." % (
                "{:,}".format(total), "" if total == 1 else "s", "" if total == 1 else "s", names, zone)}


def create_payee_dossier(session, case_id, transaction_id, user) -> dict:
    """XF-1: a payee that exists only on payments gets a person dossier named as the ledger names it. The dossier
    starts unlinked; linking it to the payee and to phone identities is a person's decision in People."""
    from postgres.models.financial import FinancialTransaction
    from services import dossier_service
    from services.financial.payment_counterparty_link import resolved_link, stored_link
    case_id = uuid.UUID(str(case_id))
    row = session.get(FinancialTransaction, uuid.UUID(str(transaction_id)))
    if row is None or row.case_id != case_id:
        raise NotInCase("That payment is not in this case.")
    link = resolved_link(session, case_id, stored_link((row.metadata_ or {}).get("investigation_labels"),
                                                       (row.provenance or {}).get("reviewed_counterparty")))
    name = ((link or {}).get("label") or row.counterparty_raw or "").strip()
    if not name:
        raise ValueError("This payment names no payee, so there is nothing to make a dossier for.")
    return dossier_service.create_dossier(session, case_id=case_id, user=user, data={
        "display_name": name[:255], "dossier_type": "person",
        "summary": "Payee on payments in this case (named on the ledger as %s). Not yet linked to anyone on the "
                   "phones or in the Graph." % name})


# ---- XF-2 ---------------------------------------------------------------------------------------------------------

def person_activity(conn, case_id, *, dossier_id=None, entity_key=None) -> dict:
    """XF-2: a Graph person (by its dossier or graph entity key) to its phone identities' messages and calls."""
    if dossier_id:
        dossiers = [dict(r._mapping) for r in conn.execute(text(
            "SELECT id::text AS id, display_name AS name FROM case_profiles WHERE case_id = :c AND id::text = :d AND "
            "archived_at IS NULL"), {"c": str(case_id), "d": str(dossier_id)})]
        if not dossiers:
            raise NotInCase("That person is not in this case.")
    else:
        dossiers = _dossiers_for_entities(conn, case_id, [entity_key] if entity_key else [])
    keys = _dossier_keys(conn, case_id, [x["id"] for x in dossiers])
    if not keys:
        return {"state": "unlinked", "people": dossiers, "total": None,
                "sentence": ("This person has no dossier yet, so nothing on the phones is linked to them."
                             if not dossiers else
                             "No phone number, address or account on the phones is linked to %s yet. Link them in "
                             "People." % dossiers[0]["name"])}
    f, href = conversations_scope(case_id, keys, zone=_zone(conn, case_id))
    total = count(conn, f)
    return {"state": "linked", "people": dossiers, "identity_keys": keys, "total": total, "conversations_href": href,
            "sentence": "%s message%s and call%s on the phones with %s." % (
                "{:,}".format(total), "" if total == 1 else "s", "" if total == 1 else "s",
                ", ".join(x["name"] for x in dossiers))}


# ---- XF-8 ---------------------------------------------------------------------------------------------------------

def counterparty_suggestions(session, case_id, identity_key: str) -> dict:
    """XF-8: accounts whose reviewed phone-number or email identifier equals this phone identity, with their
    payments. Suggested, not reviewed; nothing on the ledger changes."""
    from sqlalchemy import func, select
    from postgres.models.financial import FinancialAccount, FinancialTransaction
    from services.financial.account_identity import CONTACT_KINDS, identity_state, normalised_contact
    conn = session.connection()
    case_id = uuid.UUID(str(case_id))
    row = conn.execute(text("SELECT identity_key, value_display FROM phone_identities WHERE case_id = :c AND "
                            "identity_key = :k"), {"c": str(case_id), "k": identity_key}).first()
    if row is None:
        raise NotInCase("That phone identity is not in this case.")
    presence = money_presence.presence(conn, case_id)
    base = {"identity_key": identity_key, "label": row.value_display, "status": SUGGESTED}
    if not presence["has_financial_evidence"]:
        return {**base, "state": "no_financial_records", "sentence": money_presence.NO_FINANCIAL_RECORDS,
                "accounts": []}
    kind, _, value = identity_key.partition(":")
    accounts = []
    for account in identity_state(session, case_id)["accounts"]:
        for ident in (account.get("identity_review") or {}).get("identifiers") or []:
            if ident.get("kind") not in CONTACT_KINDS:
                continue
            want = "phone" if ident["kind"] == "phone_number" else "email"
            if want == kind and normalised_contact(ident["kind"], ident.get("value")) == value:
                acc = session.get(FinancialAccount, uuid.UUID(account["id"]))
                accounts.append({"account_id": account["id"], "identifier": ident.get("value"),
                                 "identifier_kind": ident["kind"],
                                 "label": " · ".join(v for v in (acc.holder_name, acc.institution_name,
                                                                 acc.identifier_as_printed) if v) if acc else None})
                break
    if not accounts:
        return {**base, "state": "none", "accounts": [],
                "sentence": "No reviewed account in this case uses %s as its reference." % row.value_display}
    ids = [uuid.UUID(a["account_id"]) for a in accounts]
    cond = (FinancialTransaction.case_id == case_id, FinancialTransaction.superseded_by_id.is_(None),
            FinancialTransaction.ledger_status == "admitted", FinancialTransaction.account_id.in_(ids))
    total = int(session.scalar(select(func.count()).select_from(FinancialTransaction).where(*cond)) or 0)
    payments = [{"id": str(r.id), "date": r.ordering_date.isoformat() if r.ordering_date else None,
                 "amount_minor": int(r.amount_minor), "currency": r.currency, "direction": str(r.direction.value
                 if hasattr(r.direction, "value") else r.direction), "description": r.description,
                 "account_id": str(r.account_id), "href": "/cases/%s/financial?payment=%s" % (case_id, r.id)}
                for r in session.scalars(select(FinancialTransaction).where(*cond)
                                         .order_by(FinancialTransaction.ordering_date, FinancialTransaction.id)
                                         .limit(PAYMENTS_SHOWN))]
    return {**base, "state": "suggested", "accounts": accounts, "payment_total": total, "payments": payments,
            "limitation": ("The first %d of %s payments are listed." % (len(payments), "{:,}".format(total))
                           if total > len(payments) else None),
            "sentence": "%s: %s on %d account%s whose reference is %s." % (
                SUGGESTED, "%s payment%s" % ("{:,}".format(total), "" if total == 1 else "s"), len(accounts),
                "" if len(accounts) == 1 else "s", row.value_display)}
