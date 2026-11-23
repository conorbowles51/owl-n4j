"""What is embedded in each area, read from the database as it is now (lx-embedall C).

Every reader yields ``Item`` objects: the text a person would search by (dates and amounts in words, names, labels), a
citation a hit opens, a date and the people on it. Readers read the value in effect: a superseded ledger row is not read,
so a correction embeds the corrected value only. Text a parser or model read from a page is marked ``as_read``.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Callable, Iterator

from urllib.parse import quote

from sqlalchemy import text

from services.embed_all.core import Item

AREAS = ("ledger", "accounts", "judgements", "trails", "statement_pages", "casework", "timeline", "parties",
         "transcripts", "relationships")
# Read from the graph, which has no cheap change signature: read once an hour per case (runner.HOURLY).
GRAPH_AREAS = frozenset({"relationships"})


def _day(d) -> str:
    if d is None:
        return ""
    if isinstance(d, datetime):
        d = d.date()
    return "%s %s %d (%s)" % (d.day, d.strftime("%B"), d.year, d.strftime("%A")) if isinstance(d, date) else str(d)


def _as_dt(d):
    if isinstance(d, datetime):
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    if isinstance(d, date):
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return None


def _money(minor, currency) -> str:
    if minor is None:
        return ""
    return "{:,.2f} {}".format(abs(int(minor)) / 100.0, currency or "").strip()


def _join(*parts) -> str:
    return " ".join(str(p).strip() for p in parts if p is not None and str(p).strip())


# ---------------------------------------------------------------------------------------------------- ledger

LEDGER_SQL = """
SELECT t.id, t.transaction_date, t.posted_date, t.amount_minor, t.currency, t.direction, t.description,
       t.counterparty_raw, t.transaction_type, t.bank_reference, t.ref_id, t.ledger_status, t.quarantine_reason,
       a.institution_name, a.identifier_as_printed, a.holder_name, a.account_type,
       (SELECT string_agg(DISTINCT c.category, ', ') FROM financial_payment_categories c WHERE c.transaction_id = t.id) AS cats
FROM financial_transactions t LEFT JOIN financial_accounts a ON a.id = t.account_id
WHERE t.case_id = :c AND t.superseded_by_id IS NULL AND t.ledger_status IN ('admitted', 'rejected')
ORDER BY t.id
"""


def ledger(conn, case_id) -> Iterator[Item]:
    for r in conn.execute(text(LEDGER_SQL), {"c": str(case_id)}):
        way = {"debit": "money out", "credit": "money in", "out": "money out", "in": "money in"}.get(
            str(r.direction or "").lower(), str(r.direction or ""))
        parts = [
            "Payment on %s: %s, %s." % (_day(r.transaction_date), _money(r.amount_minor, r.currency), way),
            ("Counterparty: %s." % r.counterparty_raw) if r.counterparty_raw else "",
            ("Description: %s." % r.description) if r.description else "",
            ("Reference: %s." % _join(r.bank_reference, r.ref_id)) if (r.bank_reference or r.ref_id) else "",
            ("Type: %s." % r.transaction_type) if r.transaction_type else "",
            ("Account: %s." % _join(r.institution_name, r.account_type, r.identifier_as_printed,
                                    ("held by %s" % r.holder_name) if r.holder_name else "")),
            ("Category: %s." % r.cats) if r.cats else "",
        ]
        if r.ledger_status == "rejected":
            parts.append("Set aside from the ledger%s." % ((": %s" % r.quarantine_reason) if r.quarantine_reason else ""))
        yield Item("ledger", str(r.id), " ".join(p for p in parts if p),
                   title=_join(_day(r.transaction_date), r.counterparty_raw or r.description or ""),
                   cite="txn://%s" % r.id, date=_as_dt(r.transaction_date), person=_join(r.holder_name, r.counterparty_raw))


def accounts(conn, case_id) -> Iterator[Item]:
    for r in conn.execute(text(
            "SELECT id, institution_name, identifier_as_printed, account_type, holder_name, currency, iban, bic "
            "FROM financial_accounts WHERE case_id = :c ORDER BY id"), {"c": str(case_id)}):
        body = "Account %s at %s (%s, %s)%s. Holder: %s." % (
            r.identifier_as_printed or "", r.institution_name or "", r.account_type or "account", r.currency or "",
            (" IBAN " + r.iban) if r.iban else "", r.holder_name or "not recorded")
        yield Item("accounts", str(r.id), body, title=_join(r.institution_name, r.identifier_as_printed),
                   cite="/cases/%s/financial" % case_id, person=r.holder_name or "")


def judgements(conn, case_id) -> Iterator[Item]:
    for r in conn.execute(text(
            "SELECT id, subject_type, subject_id, rule_id, reading, origin, strength, summary, status, resolution_reason, "
            "resolved_by, created_at FROM financial_judgements WHERE case_id = :c ORDER BY id"), {"c": str(case_id)}):
        body = _join("Judgement call (%s, %s):" % (r.rule_id or r.subject_type, r.status or "open"),
                     r.summary, ("Reading: %s." % r.reading) if r.reading else "",
                     ("Reason: %s." % r.resolution_reason) if r.resolution_reason else "")
        yield Item("judgements", str(r.id), body, title=(r.summary or "")[:120],
                   cite=("txn://%s" % r.subject_id) if (r.subject_type or "").startswith("transaction") and r.subject_id
                   else "/cases/%s/financial" % case_id, date=_as_dt(r.created_at),
                   as_read=(r.origin or "") != "person")


def trails(conn, case_id) -> Iterator[Item]:
    for r in conn.execute(text(
            "SELECT id, kind, details, updated_at FROM financial_money_trails WHERE case_id = :c AND active ORDER BY id"),
            {"c": str(case_id)}):
        details = r.details if isinstance(r.details, str) else json.dumps(r.details or {}, ensure_ascii=False)
        title = ""
        if isinstance(r.details, dict):
            title = str(r.details.get("name") or r.details.get("title") or "")
        yield Item("trails", str(r.id), "Saved %s: %s" % (r.kind, details[:20000]), title=title or r.kind,
                   cite="/cases/%s/financial" % case_id, date=_as_dt(r.updated_at))


def statement_pages(conn, case_id) -> Iterator[Item]:
    """Each page's text as read from the statement, held and set-aside statements included and marked."""
    rows = conn.execute(text(
        "SELECT d.id, d.evidence_file_id, d.status, d.quarantine_reason, d.institution_name, f.original_filename, "
        "t.content, t.source_locations FROM financial_source_documents d JOIN evidence_files f ON f.id = d.evidence_file_id "
        "JOIN evidence_document_texts t ON t.evidence_file_id = f.id WHERE d.case_id = :c AND d.superseded_by_id IS NULL "
        "AND f.deleted_at IS NULL ORDER BY d.id"), {"c": str(case_id)})
    for r in rows:
        note = ""
        if r.status != "admitted":
            note = "[%s statement%s] " % ("Set aside" if r.status == "rejected" else "Held",
                                           (": " + r.quarantine_reason) if r.quarantine_reason else "")
        pages = [l for l in (r.source_locations or []) if l.get("kind") == "page"]
        for loc in pages:
            body = (r.content or "")[int(loc["start_char"]):int(loc["end_char"])].strip()
            if not body:
                continue
            n = loc.get("page_number") or loc.get("label")
            yield Item("statement_pages", "%s:%s" % (r.evidence_file_id, n),
                       "%s%s, page %s, as read from the statement:\n%s" % (note, r.original_filename, n, body),
                       title="%s page %s" % (r.original_filename, n), cite="doc://%s/%s" % (r.evidence_file_id, n),
                       as_read=True)


def casework(conn, case_id) -> Iterator[Item]:
    for r in conn.execute(text(
            "SELECT id, entry_type, title, body, tags, updated_at, author_name FROM workspace_entries "
            "WHERE case_id = :c AND deleted_at IS NULL ORDER BY id"), {"c": str(case_id)}):
        tags = ", ".join(r.tags) if isinstance(r.tags, list) else ""
        body = _join("%s: %s." % ((r.entry_type or "entry").capitalize(), r.title or ""), r.body,
                     ("Tags: %s." % tags) if tags else "")
        yield Item("casework", str(r.id), body, title=r.title or "", cite="/cases/%s/workspace?view=casework&entry=%s" % (case_id, r.id),
                   date=_as_dt(r.updated_at), person=r.author_name or "")


def timeline(conn, case_id) -> Iterator[Item]:
    for r in conn.execute(text("SELECT id, event_snapshot FROM timeline_entries WHERE case_id = :c ORDER BY id"),
                          {"c": str(case_id)}):
        e = r.event_snapshot if isinstance(r.event_snapshot, dict) else json.loads(r.event_snapshot or "{}")
        when = None
        try:
            when = _as_dt(date.fromisoformat(str(e.get("date"))[:10]))
        except ValueError:
            pass
        body = _join("Timeline event on %s:" % (_day(when) if when else "an unknown date"), e.get("name"),
                     e.get("summary"), e.get("notes"), e.get("amount"), e.get("type"))
        yield Item("timeline", str(r.id), body, title=str(e.get("name") or "")[:150],
                   cite="/cases/%s/timeline?event=%s" % (case_id, e.get("key") or r.id), date=when)


def parties(conn, case_id) -> Iterator[Item]:
    for r in conn.execute(text(
            "SELECT i.id, i.identity_key, i.kind, i.value_display, i.first_instant, "
            "(SELECT string_agg(DISTINCT n.name, '; ') FROM phone_identity_names n WHERE n.identity_id = i.id) AS names, "
            "(SELECT min(n.first_record_uid::text) FROM phone_identity_names n WHERE n.identity_id = i.id) AS rec "
            "FROM phone_identities i WHERE i.case_id = :c ORDER BY i.id"), {"c": str(case_id)}):
        if not r.names and not r.value_display:
            continue
        yield Item("parties", str(r.id), "Party on the phones (%s): %s. Names recorded: %s." % (
            r.kind or "contact", r.value_display or "", r.names or "none"), title=r.names or r.value_display or "",
            cite=("rec://%s" % r.rec) if r.rec else "/cases/%s/conversations?tab=people&people=%s" % (case_id, quote(r.identity_key or "")),
            person=_join(r.names, r.value_display))


def transcripts(conn, case_id) -> Iterator[Item]:
    for r in conn.execute(text(
            "SELECT id, extraction_id, file_uid, kind, coalesce(corrected_text, text) AS body, confirmed_at, "
            "corrected_text IS NOT NULL AS corrected, created_at FROM phone_derived_texts WHERE case_id = :c "
            "AND state = 'done' ORDER BY id"), {"c": str(case_id)}):
        if not (r.body or "").strip():
            continue
        label = "Voice note transcript" if r.kind == "transcript" else "Text read from an image"
        yield Item("transcripts", str(r.id), "%s: %s" % (label, r.body), title=label,
                   cite="/cases/%s/phones/%s/records/media?file=%s" % (case_id, r.extraction_id, r.file_uid),
                   date=_as_dt(r.created_at),
                   extraction_id=str(r.extraction_id or ""), as_read=not (r.confirmed_at or r.corrected))


def _amount_text(row: dict) -> str:
    """The connection's amount; one the ledger check replaced keeps the page reading beside it."""
    if not row.get("amount"):
        return ""
    if row.get("amount_as_read") is not None:
        return "Amount: %s (the ledger amount; read from the page as %s)." % (row["amount"], row["amount_as_read"])
    return "Amount: %s." % row["amount"]


def relationship_item(case_id, row: dict, docs: dict) -> Item | None:
    """One graph connection that carries a written detail: who, how, whom, the detail, and the quotes it was read from."""
    detail = str(row.get("detail") or "").strip()
    if not detail:
        return None
    kind = str(row.get("type") or "").replace("_", " ").lower()
    quotes = row.get("quotes") or []
    if isinstance(quotes, str):
        quotes = [quotes]
    quote_text = " | ".join(str(q).replace("\n", " ") for q in quotes[:3])[:700]
    body = _join("%s %s %s." % (row.get("a") or "?", kind, row.get("b") or "?"), detail,
                 ("Date: %s." % row["date"]) if row.get("date") else "",
                 _amount_text(row),
                 ("Read from: %s" % quote_text) if quote_text else "")
    cite, page = "", None
    locs = row.get("locations") or []
    if isinstance(locs, str):
        try:
            locs = json.loads(locs)
        except ValueError:
            locs = []
    for loc in locs if isinstance(locs, list) else []:
        # The engine records the evidence file id; older locations may give the statement's own id.
        sid = str(loc.get("source_document_id") or "")
        fid = docs.get(sid) or (sid if sid in docs.values() else None)
        if fid:
            cite = "doc://%s/%s" % (fid, loc.get("page_start") or "")
            break
    return Item("relationships", str(row["id"]), body, title="%s %s %s" % (row.get("a") or "?", kind, row.get("b") or "?"),
                cite=cite or "/cases/%s/graph" % case_id, as_read=True, person=_join(row.get("a"), row.get("b")))


def relationships(conn, case_id) -> Iterator[Item]:
    """Connections between entities that have a detail, with their source quotes (the engine writes these)."""
    from services.neo4j.driver import driver
    docs = {str(r[0]): str(r[1]) for r in conn.execute(text(
        "SELECT id, evidence_file_id FROM financial_source_documents WHERE case_id = :c"), {"c": str(case_id)})}
    with driver.session() as session:
        rows = session.run(
            "MATCH (a)-[r]->(b) WHERE r.case_id = $c AND r.detail IS NOT NULL AND NOT a:RecycleBin AND NOT b:RecycleBin "
            "RETURN elementId(r) AS id, a.name AS a, type(r) AS type, b.name AS b, r.detail AS detail, r.date AS date, "
            "r.amount AS amount, r.amount_as_read AS amount_as_read, r.source_quotes AS quotes, "
            "r.source_locations AS locations", c=str(case_id))
        for row in rows:
            item = relationship_item(case_id, dict(row), docs)
            if item is not None:
                yield item


READERS: dict[str, Callable] = {"relationships": relationships, "ledger": ledger, "accounts": accounts, "judgements": judgements, "trails": trails,
                                "statement_pages": statement_pages, "casework": casework, "timeline": timeline,
                                "parties": parties, "transcripts": transcripts}

# Cheap change check per area: when it is the same as at the last sync, the area is not read again.
SIGNATURES = {
    "ledger": "SELECT concat_ws('|', (SELECT count(*) FROM financial_transactions WHERE case_id = :c), "
              "(SELECT max(updated_at)::text FROM financial_transactions WHERE case_id = :c), "
              "(SELECT count(*) || max(set_at)::text FROM financial_payment_categories WHERE case_id = :c), "
              "(SELECT max(updated_at)::text FROM financial_accounts WHERE case_id = :c))",
    "accounts": "SELECT concat_ws('|', count(*), max(updated_at)::text) FROM financial_accounts WHERE case_id = :c",
    "judgements": "SELECT concat_ws('|', count(*), max(created_at)::text, max(resolved_at)::text) FROM financial_judgements "
                  "WHERE case_id = :c",
    "trails": "SELECT concat_ws('|', count(*), max(updated_at)::text) FROM financial_money_trails WHERE case_id = :c AND active",
    "statement_pages": "SELECT concat_ws('|', count(*), max(updated_at)::text, (SELECT count(*) FROM evidence_files f WHERE "
                       "f.case_id = :c AND f.deleted_at IS NOT NULL)) FROM financial_source_documents WHERE case_id = :c",
    "casework": "SELECT concat_ws('|', count(*), max(updated_at)::text) FROM workspace_entries WHERE case_id = :c AND deleted_at IS NULL",
    "timeline": "SELECT concat_ws('|', count(*), max(updated_at)::text) FROM timeline_entries WHERE case_id = :c",
    "parties": "SELECT concat_ws('|', count(*), max(latest_modified)::text, sum(occurrences)) FROM phone_identity_names WHERE case_id = :c",
    "transcripts": "SELECT concat_ws('|', count(*), max(coalesce(corrected_at, finished_at))::text) FROM phone_derived_texts "
                   "WHERE case_id = :c AND state = 'done'",
}


# Bump when a reader changes what it makes of the same rows (the text or the citation): every area is read again, and
# only the items whose text or citation changed are embedded again (17 Nov 2026: s2 = hits open their own record).
SOURCES_VERSION = "s2"


def signature(conn, case_id, area) -> str:
    return "%s|%s" % (SOURCES_VERSION, conn.execute(text(SIGNATURES[area]), {"c": str(case_id)}).scalar() or "")
