"""Money as place and time (04 section 8.5, unit U10).

The money lane reads the ledger's own population: ``admitted`` rows (``list_transactions``' default), so a corrected
row shows only its corrected value (the original is ``superseded`` and stays one click away in the financial views).
The ledger holds dates only, so a transaction is an all-day item: on its transaction date when there is one, else on
its posted date ("the purchase may be earlier"), else on the date the ledger orders it by, named. Nothing here ever
gives a transaction a time of day.

A place on a transaction exists only when a person attaches one: a point and radius with a reason, recorded in the
case decision ledger with the person as Actor (``attach_transaction_place``; ``remove_transaction_place`` reverses
it). The earlier place stays in ``pol_manual_place`` with the decision that ended it. An attached place covers the
whole local day of the transaction.

The ledger links accounts to financial parties, not to phones or dossiers, so the lane is not narrowed by a phone
subject; a caller narrows it by accounts, and the response says which population it holds.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta

from sqlalchemy import func, select, text

from postgres.models.enums import AdjudicationDecision, AdjudicationSubject, LedgerStatus
from postgres.models.financial import FinancialTransaction
from services.financial import decisions
from services.financial.transaction_query import _ledger_rows_where

PAGE = 500
MAX_RADIUS_M = 50000.0

DATE_WORDS = {
    "transaction": "Transaction date.",
    "posted": "Posted date; the purchase may be earlier.",
    "value": "Value date; the purchase may be earlier.",
    "effective": "Effective date; the purchase may be earlier.",
    "ordering": "Date the ledger orders this row by.",
}
NO_TIME_WORDS = "Bank records hold dates only, so this payment is shown for the whole day, never at a time."
SUBJECT_WORDS = ("Bank accounts are not linked to phones or people in the ledger, so this lane shows the case's "
                 "payments, narrowed only by the accounts chosen.")


SUGGESTION_WORDS = ("A town the payment's own text names, from the offline place list. A card line can name a head "
                    "office or the card's billing town rather than where the money was spent. Nothing is saved until "
                    "a person attaches a place.")


class MoneyError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _day_expr():
    T = FinancialTransaction
    return func.coalesce(T.transaction_date, T.posted_date, T.ordering_date)


def date_basis(row) -> str:
    if row.transaction_date is not None:
        return "transaction"
    if row.posted_date is not None:
        return "posted"
    src = (row.ordering_date_source or "").lower()
    return src if src in ("value", "effective") else "ordering"


def _where(session, case_id, start_date, end_date, account_ids):
    stmt = _ledger_rows_where(select(FinancialTransaction), session, case_id, account_id=None,
                              account_ids=account_ids or None, account_holders=None,
                              ledger_status=LedgerStatus.admitted, start_date=None, end_date=None,
                              source_document_id=None)
    # admitted rows are never superseded (corrections.py sets both together); said here as well, so a row caught
    # between the two writes can never show beside its replacement
    stmt = stmt.where(FinancialTransaction.superseded_by_id.is_(None))
    if start_date is not None:
        stmt = stmt.where(_day_expr() >= start_date)
    if end_date is not None:
        stmt = stmt.where(_day_expr() <= end_date)
    return stmt


def current_places(conn, case_id, transaction_ids) -> dict:
    if not transaction_ids:
        return {}
    rows = conn.execute(text(
        "SELECT id, transaction_id, lat, lon, radius_m, reason, decision_id, actor_name, actor_email, created_at "
        "FROM pol_manual_place WHERE case_id = :c AND removed_decision_id IS NULL AND transaction_id = ANY(:t)"),
        {"c": case_id, "t": list(transaction_ids)})
    return {r.transaction_id: dict(r._mapping) for r in rows}


def day_span(day, zone):
    """The whole local day a placed transaction covers, as UTC instants."""
    start = datetime.combine(day, time(0), tzinfo=zone)
    return start, datetime.combine(day + timedelta(days=1), time(0), tzinfo=zone)


def lane(session, case_id, *, start_date=None, end_date=None, account_ids=None, zone=None, cursor=0, limit=PAGE):
    if start_date and end_date and start_date > end_date:
        raise MoneyError("The start date is after the end date.")
    base = _where(session, case_id, start_date, end_date, account_ids)
    total = session.scalar(select(func.count()).select_from(base.subquery()))
    rows = list(session.scalars(base.order_by(_day_expr(), FinancialTransaction.row_index, FinancialTransaction.id)
                                .offset(cursor).limit(limit)))
    places = current_places(session.connection(), case_id, [r.id for r in rows])
    items = []
    for r in rows:
        basis = date_basis(r)
        day = r.transaction_date or r.posted_date or r.ordering_date
        p = places.get(r.id)
        place = None
        if p:
            place = {k: p[k] for k in ("id", "lat", "lon", "radius_m", "reason", "decision_id", "actor_name",
                                       "created_at")}
            if zone is not None:
                a, b = day_span(day, zone)
                place.update(covers_start=a, covers_end=b)
        items.append({"transaction_id": r.id, "day": day, "date_basis": basis, "date_words": DATE_WORDS[basis],
                      "transaction_date": r.transaction_date, "posted_date": r.posted_date,
                      "amount_minor": r.amount_minor, "currency": r.currency, "direction": r.direction,
                      "account_id": r.account_id, "counterparty": r.counterparty_raw, "description": r.description,
                      "proof_class": r.proof_class, "time_of_day": None, "place": place})
    nxt = cursor + len(rows)
    return {"total": total, "returned": len(rows), "cursor": cursor, "limit": limit,
            "next_cursor": nxt if nxt < total else None, "items": items, "population": "admitted",
            "accounts": [str(a) for a in account_ids] if account_ids else "all", "subject_words": SUBJECT_WORDS,
            "no_time_words": NO_TIME_WORDS}


def _txn(session, case_id, transaction_id):
    t = session.get(FinancialTransaction, transaction_id)
    if t is None or str(t.case_id) != str(case_id):
        raise MoneyError("That payment is not in this case.", 404)
    if t.ledger_status != LedgerStatus.admitted.value or t.superseded_by_id is not None:
        raise MoneyError("That payment is not in the ledger's totals (it was corrected, set aside or rejected); "
                         "attach the place to the row that replaced it.", 409)
    return t


def _place_view(p):
    """The place as the decision ledger holds it: the ledger refuses floats in a snapshot (a rounded amount must
    never re-enter as a figure of record), so coordinates are decimal strings to 7 places (about 1 cm) and the
    radius whole metres."""
    if p is None:
        return None
    return {"lat": "%.7f" % p["lat"], "lon": "%.7f" % p["lon"], "radius_m": int(round(p["radius_m"]))}


def _payee_texts(t) -> list:
    """The payment's written payee as the ledger holds it, the fuller field first. Never sent in a request."""
    return [x for x in (t.description, t.counterparty_raw) if x and x.strip()]


def _payee_offers(t) -> dict:
    from services import geocoder
    for written in _payee_texts(t):
        out = geocoder.payee_candidates(written)
        if out["candidates"]:
            return out
    return {"total": 0, "returned": 0, "limit": geocoder.FORWARD_LIMIT, "candidates": [],
            "attribution": geocoder.GEONAMES_ATTRIBUTION}


def suggest_place(session, case_id, transaction_id) -> dict:
    """Towns the payment's own payee text names, from the offline place list, labelled as suggestions. Nothing is saved
    here: a place exists on a payment only when a person attaches one (``attach``)."""
    from services.pattern_of_life import text_places
    t = _txn(session, case_id, transaction_id)
    st = text_places.suggestion_status()
    off = {"enabled": False, "reason": st["reason"], "total": 0, "returned": 0, "candidates": []}
    if not st["enabled"]:
        return off
    try:
        out = _payee_offers(t)
    except LookupError as exc:
        return dict(off, reason="Suggestions are off: %s" % exc)
    return dict(out, enabled=True, reason=st["reason"], label="Suggested, not confirmed", words=SUGGESTION_WORDS)


def _offered_suggestion(t, sug):
    """What the ledger keeps of a suggestion the person used, taken from the list and not the request: a placement keeps
    only a candidate the list really offered for this payment's text."""
    if sug is None:
        return None
    from services.pattern_of_life import text_places
    try:
        wanted = text_places._clean_suggestion(sug)
    except text_places.TextPlaceError as exc:
        raise MoneyError(str(exc))
    try:
        offered = _payee_offers(t)["candidates"] if text_places.suggestion_status()["enabled"] else []
    except LookupError:
        offered = []
    for c in offered:
        if str(c["geonameid"]) == str(wanted["geonameid"]):
            return text_places._sug_snapshot(text_places._clean_suggestion(c))
    raise MoneyError("The suggestion is not one the list offered for this payment.")


def attach(session, case_id, transaction_id, *, lat, lon, radius_m, reason, actor, suggestion=None):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise MoneyError("The point is not on the map.")
    if radius_m != int(radius_m) or not (1 <= radius_m <= MAX_RADIUS_M):
        raise MoneyError("The radius is whole metres, from 1 m to 50,000 m.")
    radius_m = int(radius_m)
    if not isinstance(reason, str) or not reason.strip():
        raise MoneyError("Say why the payment was made at this place.")
    t = _txn(session, case_id, transaction_id)
    conn = session.connection()
    old = current_places(conn, case_id, [t.id]).get(t.id)
    after = {"place": _place_view({"lat": lat, "lon": lon, "radius_m": radius_m})}
    before = {"place": _place_view(old)}
    used = _offered_suggestion(t, suggestion)
    if used:   # the ledger reads a pair as a diff, so both sides name the field
        after["suggestion"], before["suggestion"] = used, None
    row = decisions.record(session, case_id=t.case_id, subject=t, subject_type=AdjudicationSubject.transaction,
                           decision=AdjudicationDecision.attach_transaction_place, reason=reason.strip(), actor=actor,
                           before=before, after=after)
    if old:
        conn.execute(text("UPDATE pol_manual_place SET removed_decision_id = :d WHERE id = :i"),
                     {"d": row.id, "i": old["id"]})
    pid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO pol_manual_place (id, case_id, target_kind, transaction_id, lat, lon, radius_m, reason, "
        "decision_id, actor_name, actor_email) VALUES (:i, :c, 'transaction', :t, :la, :lo, :r, :re, :d, :an, :ae)"),
        {"i": pid, "c": t.case_id, "t": t.id, "la": lat, "lo": lon, "r": radius_m, "re": reason.strip(), "d": row.id,
         "an": actor.name, "ae": actor.email})
    _feed(session, case_id, t.id, _place_view(old), after["place"], actor, reason.strip())
    return {"place_id": str(pid), "decision_id": str(row.id), "replaced_place_id": str(old["id"]) if old else None}


def remove(session, case_id, transaction_id, *, reason, actor):
    if not isinstance(reason, str) or not reason.strip():
        raise MoneyError("Say why the place is removed.")
    t = _txn(session, case_id, transaction_id)
    conn = session.connection()
    old = current_places(conn, case_id, [t.id]).get(t.id)
    if old is None:
        raise MoneyError("That payment has no place attached.", 409)
    row = decisions.record(session, case_id=t.case_id, subject=t, subject_type=AdjudicationSubject.transaction,
                           decision=AdjudicationDecision.remove_transaction_place, reason=reason.strip(), actor=actor,
                           before={"place": _place_view(old)}, after={"place": None})
    conn.execute(text("UPDATE pol_manual_place SET removed_decision_id = :d WHERE id = :i"),
                 {"d": row.id, "i": old["id"]})
    _feed(session, case_id, t.id, _place_view(old), None, actor, reason.strip())
    return {"decision_id": str(row.id), "removed_place_id": str(old["id"])}


def history(conn, case_id, transaction_id) -> list:
    """Every place ever attached to the payment, oldest first, with the decision that ended each."""
    return [dict(r._mapping) for r in conn.execute(text(
        "SELECT id, lat, lon, radius_m, reason, decision_id, removed_decision_id, actor_name, created_at "
        "FROM pol_manual_place WHERE case_id = :c AND transaction_id = :t ORDER BY created_at, id"),
        {"c": case_id, "t": transaction_id})]


def _feed(session, case_id, transaction_id, before, after, actor, reason):
    from services import manual_changes
    manual_changes.record_change(session, "pattern_transaction_place", case_id,
                                 {"type": "transaction", "id": str(transaction_id)}, {"place": before},
                                 {"place": after}, actor, reason, link="/cases/%s/phone-patterns" % case_id,
                                 pattern_key=manual_changes.make_pattern_key("pattern_transaction_place"))
