"""Chat passages for the case search's payments and graph entities (lx-chatcite).

A payment passage opens with one line a reader can check: date, amount, direction, counterparty, account and the
statement page, then the case search's own text (the row with its month). Its citation is ``txn://<id>``. A graph
entity passage is the entity with its aliases and links; its citation is ``entity://<key>``. Both citations open
the record in the app, and ``services.case_citations`` checks them against the case before an answer is kept.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable
from urllib.parse import quote, unquote

from sqlalchemy import text

logger = logging.getLogger(__name__)


def _money(minor: Any, currency: str | None) -> str:
    return ("%s %.2f" % (currency or "", (minor or 0) / 100.0)).strip()


def payment_facts(conn, case_id, txn_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """The facts of each payment of the case among ``txn_ids``, read from the ledger row itself. An id that is not a
    row of this case is absent from the result."""
    ids = sorted({str(i) for i in txn_ids})
    if not ids:
        return {}
    rows = conn.execute(text(
        "SELECT t.id::text AS id, t.transaction_date, t.ordering_date, t.amount_minor, t.currency, t.direction, "
        "t.counterparty_raw, t.description, t.ledger_status, t.superseded_by_id, a.institution_name, "
        "a.identifier_as_printed, a.holder_name, t.provenance -> 'locator' ->> 'page' AS page "
        "FROM financial_transactions t LEFT JOIN financial_accounts a ON a.id = t.account_id "
        "WHERE t.case_id = :c AND t.id::text = ANY(:ids)"), {"c": str(case_id), "ids": ids}).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        day = r.transaction_date or r.ordering_date
        way = "out" if str(r.direction or "").lower() in ("debit", "out") else "in"
        account = " ".join(p for p in (r.institution_name, r.identifier_as_printed) if p)
        if r.holder_name:
            account = ("%s (%s)" % (account, r.holder_name)) if account else r.holder_name
        page = int(r.page) if str(r.page or "").isdigit() and int(r.page) >= 1 else None
        parts = ["Payment", str(day) if day else "date not given", "%s %s" % (_money(r.amount_minor, r.currency), way)]
        who = (r.counterparty_raw or r.description or "").strip()
        if who:
            parts.append(("to " if way == "out" else "from ") + who[:120])
        if account:
            parts.append("account " + account)
        parts.append("statement page %d" % page if page else "statement page not given")
        if r.ledger_status and r.ledger_status != "admitted":
            parts.append("ledger status %s" % r.ledger_status)
        if r.superseded_by_id:
            parts.append("replaced by a later row")
        out[r.id] = {"line": " · ".join(parts), "page": page}
    return out


def entity_cite(key: str) -> str:
    """``entity://<key>``; a key with characters a link cannot hold is percent-encoded, and read back the same."""
    return "entity://" + quote(key, safe="-_.~:")


def passage(hit: dict[str, Any], cite: str, facts: dict[str, dict[str, Any]], case_id) -> dict[str, Any] | None:
    """The chat passage for a ``txn://`` or ``entity://`` hit, or None when the hit is not one of those or its row
    is not in the case. The passage has no page: a statement page is part of its first line, never the header's."""
    if cite.startswith("entity://"):
        cite = entity_cite(unquote(cite[9:]))
    meta: dict[str, Any] = {"case_id": str(case_id), "doc_name": hit.get("title") or "", "filename": hit.get("title") or "",
                            "case_search_grade": hit["grade"], "case_search_reason": hit.get("reason"), "cite": cite,
                            "source_kind": "payment" if cite.startswith("txn://") else "graph_entity"}
    body = hit.get("text") or ""
    if cite.startswith("txn://"):
        known = facts.get(cite[6:].lower())
        if known is None:
            return None
        body = known["line"] + "\n" + body
        meta["doc_name"] = meta["filename"] = "Payment: " + (hit.get("title") or cite[6:])[:100]
    elif not cite.startswith("entity://"):
        return None
    return {"id": "case:%s" % cite, "text": body, "metadata": meta, "_case_search": True}
