"""What the phones hold around the payments a ledger read returned (followups 22 Nov 2026).

Live, 22 Nov: 'What comes before each of those checks?' was answered from the ledger rows alone, three runs in a row,
although the case's phones held the price list emailed six days before one of the checks; a prompt line saying to
read every source did not change it. A ledger read that returns payments now says, from the records, how many
messages, calls and emails the phones hold in the week before each payment, with the phone read that lists them.
Counts only: nothing is linked to a payment and nothing is read as its purpose (get_payment_conversation does that
once the two people have reviewed identities).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

DAYS_BEFORE = 7
PER_PAYMENT = 10  # up to this many payments, each gets its own window; more share one span

_KINDS = (("message", "messages"), ("call", "calls"), ("email", "emails"))  # the words counted


def _day(item: dict) -> date | None:
    for key in ("transaction_date", "posted_date", "ordering_date"):
        v = item.get(key)
        if isinstance(v, date):
            return v
        if isinstance(v, str) and len(v) >= 10:
            try:
                return date.fromisoformat(v[:10])
            except ValueError:
                continue
    return None


def _counts(conn, case_id, first: date, last: date) -> dict:
    """The counts of the list the window's read_with call returns: the filter phone_messages builds for that
    start and end with include_groups, so 'records' equals that read's total."""
    from services.agent.phone_tools import _instant
    from services.phone import streams
    from services.phone.filters import StreamFilter
    a, b = _instant(first.isoformat()), _instant(last.isoformat(), end=True)
    f = StreamFilter.model_validate({
        "case_id": str(case_id), "phones": [], "participants": [], "participant_mode": "any",
        "group_scope": "include_groups", "kinds": [], "from_instant": a, "to_instant": b, "include_no_time": False,
        "text": {"query": ""}, "zone": {"mode": "case"}})
    c = streams.index_comm_events(conn, f)["counts"]
    events, calls, messages = int(c.get("events") or 0), int(c.get("calls") or 0), int(c.get("messages") or 0)
    return {"records": events, "messages": messages, "calls": calls, "emails": events - calls - messages}


def _has_phone_records(conn, case_id) -> bool:
    """Phone records live in PostgreSQL only; one read, a SELECT, so a read-only ledger session stays read-only."""
    from sqlalchemy import text
    if conn.dialect.name != "postgresql":
        return False
    return conn.execute(text("SELECT 1 FROM pv_comm_event WHERE case_id = :c LIMIT 1"),
                        {"c": str(case_id)}).first() is not None


def _read_call(first: date, last: date) -> str:
    return "phone_messages(start='%s', end='%s', include_groups=true)" % (first.isoformat(), last.isoformat())


def around(conn, case_id, items: Iterable[dict]) -> dict | None:
    """``None`` when the case has no phone records or no returned row has a day; otherwise the windows (the
    ``DAYS_BEFORE`` days before each payment's day, through that day, whole UTC days as phone_messages reads
    them) with their counts."""
    rows = [(it, _day(it)) for it in items or ()]
    rows = [(it, d) for it, d in rows if d is not None]
    if not rows:
        return None
    if not _has_phone_records(conn, case_id):
        return None
    windows: list[dict[str, Any]] = []
    if len(rows) <= PER_PAYMENT:
        for it, d in rows:
            first = d - timedelta(days=DAYS_BEFORE)
            c = _counts(conn, case_id, first, d)
            ref = it.get("transaction_id") or it.get("id")
            windows.append({"payment": "txn://%s" % ref if ref else None,
                            "description": it.get("description"), "day": d.isoformat(),
                            "start": first.isoformat(), "end": d.isoformat(), **c,
                            "read_with": _read_call(first, d) if any(c.values()) else None})
    else:
        days = [d for _, d in rows]
        first, last = min(days) - timedelta(days=DAYS_BEFORE), max(days)
        c = _counts(conn, case_id, first, last)
        windows.append({"payment": None, "description": "%d payments" % len(rows), "day": None,
                        "start": first.isoformat(), "end": last.isoformat(), **c,
                        "read_with": _read_call(first, last) if any(c.values()) else None})
    held = [w for w in windows if any(w[k] for _, k in _KINDS)]
    if not held:
        return None
    if len(rows) <= PER_PAYMENT:
        lead = "The phones hold messages, calls or emails in the %d days before %d of these %d payments" % (
            DAYS_BEFORE, len(held), len(rows))
    else:
        w = held[0]
        lead = ("The phones hold %d messages, %d calls and %d emails from %d days before the first of these %d "
                "payments to the last" % (w["messages"], w["calls"], w["emails"], DAYS_BEFORE, len(rows)))
    sentence = (lead + " (counted in around_on_phones.windows, not read). What came before or around a payment may "
                "be in them: read a window with its read_with call, or search_case with a name and the same start "
                "and end.")
    return {"days_before": DAYS_BEFORE, "days_in": "UTC, as phone_messages reads a day", "windows": windows,
            "sentence": sentence,
            "note": "Counts of the records on the phones in each window, copies on two phones counted once. They "
                    "are not linked to the payments and say nothing of their purpose."}


def statement_payments(db, case_id, evidence_file_id) -> list[dict]:
    """The current ledger rows read from a statement file (admitted, not superseded), for ``around``. Empty when the
    file is not a ledger statement (followups 23 Nov: a follow-up that read the statement's text, not the ledger,
    was never told what the phones hold before its payments)."""
    from sqlalchemy import select

    from postgres.models.financial import FinancialSourceDocument as Source
    from postgres.models.financial import FinancialTransaction as Payment
    rows = db.execute(
        select(Payment.id, Payment.transaction_date, Payment.posted_date, Payment.description)
        .join(Source, Source.id == Payment.source_document_id)
        .where(Source.case_id == case_id, Source.evidence_file_id == evidence_file_id, Source.superseded_by_id.is_(None),
               Payment.case_id == case_id, Payment.ledger_status == "admitted", Payment.superseded_by_id.is_(None))
        .order_by(Payment.transaction_date, Payment.id))
    return [{"transaction_id": str(r.id), "transaction_date": r.transaction_date, "posted_date": r.posted_date,
             "description": r.description} for r in rows]
