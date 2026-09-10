"""Chronology of captured ledger readings; dates never imply event correlation."""
import json
from services.financial.ledger_summary import LedgerSummaryError

MAX_TIMELINE_ROWS = 1000


def ledger_timeline(export, *, population="working"):
    if population not in ("working", "verified"):
        raise LedgerSummaryError("Choose working or verified readings.")
    document = json.loads(export.snapshot.content)
    ledger = document["ledger"]
    if not document.get("export_ready") or not ledger.get("history_captured"):
        raise LedgerSummaryError("Timeline requires a consistent captured ledger and history.")
    eligible = [r for r in ledger["readings"] if (
        r["exclusion_reason"] in (None, "proof_class_not_included")
        if population == "working" else r["included"]
    )]
    if len(eligible) > MAX_TIMELINE_ROWS:
        raise LedgerSummaryError("More than 1,000 current readings match. Narrow the account or ordering-date scope; no partial chronology was returned.")
    rows = []
    for reading in eligible:
        row = reading["row"]
        basis = next((field for field in ("value_date", "transaction_date", "posted_date", "effective_date") if row.get(field)), "ordering_date")
        if row.get("ordering_date_context") == "statement_end_ordering_only":
            basis = "statement_end_ordering_only"
        rows.append(dict(
            **row,
            chronology_date=row["ordering_date"] if basis == "statement_end_ordering_only" else row[basis],
            chronology_basis=basis,
            account_label=reading.get("account", {}).get("label") or "Account " + row["account_id"][:8],
        ))
    rows.sort(key=lambda r: (r["chronology_date"], r["key"]))
    return dict(
        case_id=ledger["case_id"], account_id=ledger["account_id"],
        start_date=ledger["start_date"], end_date=ledger["end_date"],
        population=population, snapshot_sha256=export.snapshot.sha256,
        rows=rows, excluded_rows=len(ledger["readings"])-len(eligible),
        limitation="Ledger scope uses ordering dates. Display uses value date, then transaction, posted, effective or ordering date, explicitly labelled. A displayed date can fall outside the ordering-date filter. Same-day position does not establish sequence. Case events are context, not matched or corroborated payments.",
    )
