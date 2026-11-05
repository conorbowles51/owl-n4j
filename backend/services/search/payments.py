"""The ``payments`` search group: ledger rows of the case by description, counterparty or amount, with totals.

What is searched, all in the values in use now (a corrected value replaces the one it corrects, and an old value
kept in a row's history is never searched): the printed description, the printed counterparty, a sender or
recipient name a person saved on the payment, the label of a counterparty a person linked, the account holder, and
the amount (``1234.56``, ``1,234.56`` or ``$1,234.56`` matches the payment of exactly that amount in any currency
with two decimals; whole-unit currencies the same way). A name Loupe only suggests (a matched party, a name read from
the description) is not searched, and the group says so.

Rows are the admitted ledger rows the Financial page lists. The totals are per currency and direction over the
matching rows that are not replaced and come from an admitted statement, in two populations that are never added
together: ``verified`` (row and statement both p0 to p2) and ``p3`` (read from a statement, not verified; a row
counts at the weaker of its own class and its statement's). Matching rows outside both are counted, never summed. Each hit cites its row
by ``txn://`` and opens the Financial page on that payment, at its statement page.
"""
from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

NOT_SEARCHED = ("Names Loupe suggests for a payment (a matched party, or a name read from the description) are not "
                "searched; the printed text, names a person saved, linked counterparties, account holders and amounts "
                "are.")
_AMOUNT = re.compile(r"^\s*[-+]?\s*[$€£¥]?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.([0-9]{1,3}))?\s*$")


def _like(q: str) -> str:
    return "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def amount_query(q: str) -> Decimal | None:
    match = _AMOUNT.match(q or "")
    if not match:
        return None
    whole, fraction = match.group(1).replace(",", ""), match.group(2) or ""
    try:
        return Decimal(f"{whole}.{fraction}" if fraction else whole)
    except InvalidOperation:
        return None


def _payments_where(session, case_id, q):
    from postgres.models.financial import FinancialAccount, FinancialTransaction as T
    labels = T.metadata_["investigation_labels"]
    lowered = _like(q)
    text_fields = [T.description, T.counterparty_raw, labels["from_name"].as_string(), labels["to_name"].as_string(),
                   labels["counterparty_link"]["label"].as_string(), FinancialAccount.holder_name]
    matches = [func.lower(field).like(lowered, escape="\\") for field in text_fields]
    value = amount_query(q)
    if value is not None:
        currencies = [row[0] for row in session.execute(select(T.currency).where(T.case_id == case_id).distinct())]
        from services.financial.money import get_currency
        for currency in currencies:
            try:
                exponent = get_currency(currency).exponent
            except Exception:  # noqa: BLE001 - an unknown code is not searched by amount
                continue
            minor = value.scaleb(exponent)
            if minor == minor.to_integral_value():
                matches.append(and_(T.currency == currency, T.amount_minor == int(minor)))
    return [T.case_id == case_id, T.ledger_status == "admitted", or_(*matches)]


def search_payments(conn, case_id, q, *, offset=0, limit=20):
    """``(total, items, totals)`` for ``q`` in the case's ledger; ``totals`` is the money of every matching row."""
    from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialTransaction as T
    from services.case_citations import txn_href
    from services.financial.proof_class import DEFAULT_TOTAL_CLASSES
    from services.financial.transaction_query import to_view
    case_id = case_id if isinstance(case_id, uuid.UUID) else uuid.UUID(str(case_id))
    session = Session(bind=conn)
    try:
        where = _payments_where(session, case_id, q)
        joined = (select(T.id).select_from(T).join(FinancialAccount, FinancialAccount.id == T.account_id)
                  .outerjoin(FinancialSourceDocument, FinancialSourceDocument.id == T.source_document_id))
        verified = sorted(p.value for p in DEFAULT_TOTAL_CLASSES)
        working = verified + ["p3"]
        # a row counts at the weaker of its own class and its statement's class
        counted = and_(T.superseded_by_id.is_(None), FinancialSourceDocument.status == "admitted",
                       T.proof_class.in_(working), FinancialSourceDocument.proof_class.in_(working))
        population = case((and_(T.proof_class.in_(verified), FinancialSourceDocument.proof_class.in_(verified)),
                           "verified"), else_="p3")
        total = int(session.scalar(select(func.count()).select_from(joined.where(*where).subquery())) or 0)
        sums = session.execute(
            select(T.currency, T.direction, population, func.count(), func.sum(T.amount_minor))
            .select_from(T).join(FinancialAccount, FinancialAccount.id == T.account_id)
            .outerjoin(FinancialSourceDocument, FinancialSourceDocument.id == T.source_document_id)
            .where(*where, counted).group_by(T.currency, T.direction, population)
            .order_by(T.currency, T.direction)).all()
        totals = {}
        for currency, direction, bucket, count, amount in sums:
            entry = totals.setdefault(currency, {"currency": currency, **{
                name: {"credits_minor": "0", "debits_minor": "0", "credit_count": 0, "debit_count": 0}
                for name in ("verified", "p3")}})
            entry[bucket][f"{direction}s_minor"] = str(int(amount or 0))
            entry[bucket][f"{direction}_count"] = int(count)
        counted_rows = sum(int(row[3]) for row in sums)
        if not total or not limit:
            return total, [], {"currencies": list(totals.values()), "counted_rows": counted_rows,
                               "not_counted_rows": total - counted_rows}
        ids = [row[0] for row in session.execute(
            joined.where(*where).order_by(T.ordering_date.desc().nulls_last(), T.row_index, T.id)
            .offset(offset).limit(limit))]
        rows = {row.id: row for row in session.scalars(select(T).where(T.id.in_(ids)))}
        counts = {row[0] for row in session.execute(
            select(T.id).select_from(T).outerjoin(FinancialSourceDocument,
                                                  FinancialSourceDocument.id == T.source_document_id)
            .where(T.id.in_(ids), counted))}
        from services.financial.transaction_numbers import attach_numbers
        attach_numbers(session, rows.values())
        items = []
        for identifier in ids:
            row = rows[identifier]
            view = to_view(row, account=row.account).to_json()
            title = view.get("description") or view.get("counterparty_raw") or "Payment"
            items.append({
                "kind": "payment", "title": title,
                "snippet": _snippet(q, view),
                "transaction_id": str(row.id), "cite": txn_href(row.id),
                "date": view.get("ordering_date"), "amount_minor": str(row.amount_minor), "currency": row.currency,
                "direction": row.direction, "from_name": view.get("from_name"), "to_name": view.get("to_name"),
                "account_label": view.get("account_label"), "included_in_totals": row.id in counts,
                "page": (view.get("locator") or {}).get("page") if isinstance(view.get("locator"), dict) else None,
                "record_uid": None, "evidence_file_id": None,
                "open": {"screen": "payment", "params": {"transaction_id": str(row.id)}}})
        return total, items, {"currencies": list(totals.values()), "counted_rows": counted_rows,
                              "not_counted_rows": total - counted_rows}
    finally:
        session.close()


def _snippet(q, view):
    lowered = q.lower()
    for field in ("description", "counterparty_raw", "from_name", "to_name", "account_holder"):
        value = view.get(field) or ""
        at = value.lower().find(lowered)
        if at >= 0:
            return {"before": value[max(0, at - 60):at], "match": value[at:at + len(q)],
                    "after": value[at + len(q):at + len(q) + 60], "field": field}
    return {"before": "", "match": "", "after": view.get("description") or "", "field": "amount"}
