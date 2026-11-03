"""The agent's reader of a case's trades and holdings (lx-brokerage D; report rank 18, scenario 6).

Keeps the ledger-tool contract (``ledger_reading_tools``): the case comes from the run, never the model; the session
is the read-only one the runner opens; a page states ``total``, ``returned``, ``offset`` and ``next_offset``; a
``revision`` pins what was read; every item carries a citation (file, page, the printed line, an in-app link, and
for a trade its cash leg in the money ledger). The corrected value is the one returned; the value as read is beside
it. A model's reading says so (``origin.kind == "model"``) until a person confirms it. Arithmetic (the quantity and
net totals per instrument) is done here, never by the model.

The trade date is the printed operation day; these statements print no time of execution, and a trade never carries
one it did not print (``not_printed``). Set a trade against calls and messages by its date only.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from services.agent.ledger_reading_tools import (LedgerReadingError, _day, _page, _revision, _unavailable,
                                                 formatted, payment_href)

MONEY = ("net", "gross", "commission", "premium", "tax", "market_value")

SCHEMA = "loupe.agent.trades/1"
NOT_IN_CASE = "That account is not in this case."


def trades_href(case_id, row_id):
    return "/cases/%s/financial?view=trades&security=%s" % (case_id, row_id)


def get_trades(db, *, case_id, kind="trade", instrument=None, account_id=None, side=None, date_from=None,
               date_to=None, offset=0, limit=25):
    from sqlalchemy import select
    from postgres.models.financial import FinancialAccount
    from services.financial import brokerage_ledger as BL
    offset, limit = _page(offset, limit)
    if kind not in ("trade", "holding"):
        raise LedgerReadingError("kind is trade or holding.")
    start, end = _day(date_from), _day(date_to)
    account = None
    if account_id:
        try:
            account = UUID(str(account_id))
        except ValueError as exc:
            raise LedgerReadingError("Use a valid account id.") from exc
        owner = db.scalar(select(FinancialAccount.case_id).where(FinancialAccount.id == account))
        if owner != case_id:
            return _unavailable(SCHEMA, case_id, NOT_IN_CASE)
    # Every matching row is read (pages of the service's maximum) so the totals cover them all, not one page.
    rows, page, revision, hidden = [], 1, None, 0
    while True:
        chunk = BL.query_rows(db, case_id=case_id, row_kind=kind, instrument=instrument, account_id=account,
                              side=side, date_from=start, date_to=end, page=page, page_size=BL.MAX_PAGE)
        rows.extend(chunk["items"])
        revision, hidden = chunk["revision"], chunk["not_shown_cash_leg_not_in_ledger"]
        if not chunk["next_page"]:
            break
        page = chunk["next_page"]
    items = [_item(case_id, r) for r in rows]
    totals = _totals(rows, kind)
    reading_by = {}
    for r in rows:
        reading_by[r["origin"]["kind"]] = reading_by.get(r["origin"]["kind"], 0) + 1
    window = items[offset:offset + limit]
    nxt = offset + limit if offset + limit < len(items) else None
    return dict(schema=SCHEMA, case_id=str(case_id), available=True, reason=None,
                revision=_revision([revision, len(items), [i["id"] for i in items]]),
                total=len(items), returned=len(window), offset=offset, has_more=nxt is not None, next_offset=nxt,
                items=window, totals_by_instrument=totals, readings_by_origin=reading_by,
                not_shown_cash_leg_not_in_ledger=hidden,
                note=("Trade date is the printed operation day; no time of execution is printed. Rows with origin "
                      "kind 'model' were read by a model and no person has confirmed them."))


def _item(case_id, r):
    citation = dict(r["citation"])
    citation["href"] = trades_href(case_id, r["id"])
    if r.get("cash_transaction_id"):
        citation["cash_leg_href"] = payment_href(case_id, r["cash_transaction_id"])
    return dict(
        id=r["id"], kind=r["row_kind"], side=r["side"], holding_kind=r["holding_kind"], operation=r["operation"],
        instrument=r["instrument"], isin=r["isin"], quantity=r["quantity"], price=r["price"], currency=r["currency"],
        net_minor=r["net_minor"], gross_minor=r["gross_minor"], commission_minor=r["commission_minor"],
        premium_minor=r["premium_minor"], tax_minor=r["tax_minor"], market_value_minor=r["market_value_minor"],
        trade_date=r["trade_date"], settlement_date=r["settlement_date"], as_of_date=r["as_of_date"],
        execution_time=r["execution_time"], term_days=r["term_days"], rate=r["rate_printed"],
        account=r["account"], account_id=r["account_id"], file=r["file"], proof_class=r["proof_class"],
        origin=r["origin"], corrections={k: dict(read=v.get("read"), value=v.get("value"), by=(v.get("by") or {}).get("name"))
                                         for k, v in (r.get("corrections") or {}).items()},
        not_printed=r["not_printed"], not_read=r["not_read"], checks=r["checks"], citation=citation,
        # Each minor-unit figure beside its formatted amount, so a model never reads centavos as pesos.
        currency_exponent=formatted(0, r["currency"])["currency_exponent"],
        **{m: formatted(r[m + "_minor"], r["currency"])["amount"] if r[m + "_minor"] is not None else None
           for m in MONEY})


def _totals(rows, kind):
    """Per instrument and currency: rows, quantity bought and sold (trades) or held at the latest date (holdings),
    and net cash (trades). Rows whose quantity was not read are counted, never summed."""
    groups = {}
    for r in rows:
        key = (r["instrument"], r["currency"])
        g = groups.setdefault(key, dict(instrument=r["instrument"], currency=r["currency"], rows=0,
                                        quantity_not_read=0, quantity_in=Decimal(0), quantity_out=Decimal(0),
                                        net_paid_minor=0, net_received_minor=0, latest=None))
        g["rows"] += 1
        quantity = Decimal(r["quantity"]) if r["quantity"] not in (None, "") else None
        if quantity is None:
            g["quantity_not_read"] += 1
        if kind == "holding":
            day = r["as_of_date"] or ""
            if quantity is not None and (g["latest"] is None or day > g["latest"][0]):
                g["latest"] = (day, quantity, r["market_value_minor"])
            continue
        incoming = r["side"] in ("buy", "repo_start")
        outgoing = r["side"] in ("sell", "repo_maturity")
        if quantity is not None:
            if incoming:
                g["quantity_in"] += quantity
            elif outgoing:
                g["quantity_out"] += quantity
        if r["net_minor"] is not None:
            if (r["citation"].get("cash_leg") or {}).get("direction") == "credit":
                g["net_received_minor"] += int(r["net_minor"])
            else:
                g["net_paid_minor"] += int(r["net_minor"])
    out = []
    for g in groups.values():
        latest = g.pop("latest")
        g["currency_exponent"] = formatted(0, g["currency"])["currency_exponent"]
        if kind == "holding":
            value = latest[2] if latest else None
            g.update(latest_as_of=latest[0] if latest else None,
                     latest_quantity=str(latest[1]) if latest else None,
                     latest_market_value_minor=value,
                     latest_market_value=formatted(value, g["currency"])["amount"] if value is not None else None)
            for k in ("quantity_in", "quantity_out", "net_paid_minor", "net_received_minor"):
                g.pop(k)
        else:
            g["quantity_in"], g["quantity_out"] = str(g["quantity_in"]), str(g["quantity_out"])
            g["net_paid"] = formatted(g["net_paid_minor"], g["currency"])["amount"]
            g["net_received"] = formatted(g["net_received_minor"], g["currency"])["amount"]
        out.append(g)
    return sorted(out, key=lambda g: (g["instrument"], g["currency"] or ""))
