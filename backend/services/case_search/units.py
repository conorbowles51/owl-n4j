"""Results big enough to judge (plan R3): each hit becomes a whole unit.

- Phone messages: the message window as the search returned it (consecutive lines of one thread around the match,
  each line citing its record), never a 60-character snippet.
- Document passages and statement pages: the passage or page text.
- Statement rows: the row, then the other rows of the same account in the same month (date, amount, counterparty),
  so a payment is read beside its neighbours.
- Graph entities: name, type, summary, aliases and links (relationship and the linked entity).
- Everything else (notes, timeline events, parties, transcripts, accounts): the indexed text in full.

A unit longer than ``UNIT_CHARS`` is cut around the matched words, and the cut is said in the unit (how many
characters are left out and how to read the whole). Never silent.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

UNIT_CHARS = 4000
MONTH_ROWS = 30
LINKS = 15
READ_WHOLE = {"phone_text": "phone_messages for the thread and window", "documents": "get_document_text",
              "statement_pages": "get_document_text", "transcripts": "get_transcript"}


def _cut(body: str, terms: list[str], area: str) -> tuple[str, int]:
    body = body or ""
    if len(body) <= UNIT_CHARS:
        return body, 0
    low = body.casefold()
    at = next((low.find(t.casefold()) for t in terms if low.find(t.casefold()) >= 0), 0)
    start = max(0, min(len(body) - UNIT_CHARS, at - UNIT_CHARS // 3))
    left = len(body) - UNIT_CHARS
    how = READ_WHOLE.get(area)
    note = "[%d characters of this record are not shown%s.]" % (left, ("; read the whole with %s" % how) if how else "")
    return (("…" if start else "") + body[start:start + UNIT_CHARS] + ("…" if start + UNIT_CHARS < len(body) else "")
            + "\n" + note), left


def _ledger_month(conn, case_id, txn_id: str) -> str | None:
    row = conn.execute(text(
        "SELECT account_id, transaction_date FROM financial_transactions WHERE id::text = :t AND case_id = :c"),
        {"t": txn_id, "c": str(case_id)}).first()
    if row is None or row.account_id is None or row.transaction_date is None:
        return None
    d = row.transaction_date
    rows = conn.execute(text(
        "SELECT id, transaction_date, amount_minor, currency, direction, counterparty_raw, description FROM "
        "financial_transactions WHERE case_id = :c AND account_id = :a AND superseded_by_id IS NULL AND ledger_status = "
        "'admitted' AND date_trunc('month', transaction_date) = date_trunc('month', CAST(:d AS date)) ORDER BY "
        "transaction_date, id"), {"c": str(case_id), "a": row.account_id, "d": d}).fetchall()
    if not rows:
        return None
    me = next((i for i, r in enumerate(rows) if str(r.id) == txn_id), 0)
    lo = max(0, min(len(rows) - MONTH_ROWS, me - MONTH_ROWS // 2))
    shown = rows[lo:lo + MONTH_ROWS]
    lines = []
    for r in shown:
        amt = "%s %.2f" % (r.currency or "", (r.amount_minor or 0) / 100.0)
        way = "out" if str(r.direction or "").lower() in ("debit", "out") else "in"
        mark = "  <- this row" if str(r.id) == txn_id else ""
        lines.append("%s  %s %s  %s [txn://%s]%s" % (r.transaction_date, amt.strip(), way,
                                                     (r.counterparty_raw or r.description or "")[:80], r.id, mark))
    head = "The account's rows in %s (%d of %d shown):" % (d.strftime("%B %Y"), len(shown), len(rows))
    return head + "\n" + "\n".join(lines)


def _entity(case_id, key: str) -> str | None:
    from services.neo4j.graph_service import graph_service
    d = graph_service.get_node_details(key, case_id=str(case_id))
    if not d:
        return None
    props = d.get("properties") or {}
    aliases = props.get("aliases") or props.get("alias") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    links = d.get("connections") or []
    parts = ["%s (%s)." % (d.get("name") or key, d.get("type") or "entity")]
    if d.get("summary"):
        parts.append(str(d["summary"]))
    if aliases:
        parts.append("Also known as: %s." % ", ".join(str(a) for a in aliases[:20]))
    if links:
        shown = links[:LINKS]
        parts.append("Links (%d of %d shown): %s." % (len(shown), len(links), "; ".join(
            "%s %s (%s)" % (c.get("relationship") or c.get("type") or "linked to", c.get("name") or c.get("key"),
                            c.get("key")) for c in shown)))
    return " ".join(parts)


def build(conn, case_id, hit: dict[str, Any], terms: list[str]) -> dict[str, Any]:
    """The hit's ``text`` made a whole unit, in place; ``unit`` names what the unit holds."""
    area = hit["area"]
    body = hit.get("text") or ""
    unit = {"phone_text": "message window", "documents": "passage", "statement_pages": "statement page",
            "ledger": "statement row with its month", "graph": "entity with aliases and links"}.get(area, "record")
    try:
        if area == "ledger" and (hit.get("cite") or "").startswith("txn://"):
            with conn.begin_nested():
                month = _ledger_month(conn, case_id, hit["cite"][6:])
            if month:
                body = body + "\n" + month
        elif area == "graph":
            ent = _entity(case_id, hit["key"])
            if ent:
                body = ent
    except Exception:  # noqa: BLE001 - the hit stays as found, said so
        logger.warning("Unit could not be widened for %s %s", area, hit.get("key"), exc_info=True)
        hit["unit_note"] = "Shown as found; its wider context could not be read."
    hit["text"], hit["chars_not_shown"] = _cut(body, terms, area)
    hit["unit"] = unit
    return hit
