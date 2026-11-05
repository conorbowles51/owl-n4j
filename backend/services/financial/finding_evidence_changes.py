"""What changed in a finding's cited payments since they were cited.

A finding keeps the values it cited (``metadata.transactions`` on its links) and those are never rewritten. This
read compares each saved value with the payment as the ledger now has it, following a correction to its current
row, and says what differs. It writes nothing and changes no citation.

Compared: the facts a citation shows (amount, currency, direction, date, description, printed reference) and any
label a person saved on the payment. A description-based guess at a category or name is not compared: such a guess
is re-derived on each read and moves when a rule moves, with no change to the payment.
Reverse: add a field to ``FIELDS``, or drop the ``labels`` check, here.

A citation with no saved values can still show a payment corrected, set aside or gone, but not what changed in it;
it is counted in ``not_compared``, so a clean mark is never claimed for values that were not compared.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from postgres.models.financial import FinancialTransaction as Payment
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services.financial.transaction_query import description_correction

MAX_ENTRIES = 100
FIELDS = (
    ("amount_minor", "Amount"), ("currency", "Currency"), ("direction", "Direction"),
    ("ordering_date", "Date"), ("description", "Description"), ("bank_reference", "Printed reference"),
)
LABELS = (("category", "Category"), ("from_name", "From"), ("to_name", "To"))
COLUMNS = (Payment.id, Payment.case_id, Payment.ref_id, Payment.amount_minor, Payment.currency, Payment.direction,
           Payment.ordering_date, Payment.description, Payment.bank_reference, Payment.ledger_status,
           Payment.superseded_by_id, Payment.metadata_, Payment.provenance)


class EvidenceChangeError(ValueError):
    pass


def _text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _load(db: Session, case_id: UUID, ids: set[str]) -> dict[str, Payment]:
    """The rows with these ids, then their replacements until none is new: one query per correction step."""
    rows: dict[str, Payment] = {}
    pending = set(ids)
    while pending:
        found = db.scalars(select(Payment).options(load_only(*COLUMNS, raiseload=True)).where(
            Payment.id.in_([UUID(value) for value in pending]), Payment.case_id == case_id)).all()
        rows.update({str(row.id): row for row in found})
        pending = {str(row.superseded_by_id) for row in found if row.superseded_by_id} - set(rows)
    return rows


def _current(row: Payment, rows: dict[str, Payment]) -> Payment:
    seen = {str(row.id)}
    while row.superseded_by_id is not None:
        key = str(row.superseded_by_id)
        if key in seen or key not in rows:
            break
        seen.add(key)
        row = rows[key]
    return row


def _differences(saved: dict[str, Any], row: Payment) -> list[dict[str, Any]]:
    changes = []
    for field, label in FIELDS:
        if field in saved and _text(saved[field]) != _text(getattr(row, field)):
            change = dict(field=field, label=label, cited=_text(saved[field]), current=_text(getattr(row, field)))
            model = description_correction(row) if field == "description" else None
            if model:  # a model's reading stays labelled as one until a person confirms it
                change["reading"] = f"Read by {model['model']} · not confirmed"
            changes.append(change)
    labels = (row.metadata_ or {}).get("investigation_labels") or {}
    for field, label in LABELS:
        if field in labels and field in saved and _text(saved[field]) != _text(labels[field]):
            changes.append(dict(field=field, label=label, cited=_text(saved[field]), current=_text(labels[field])))
    return changes


def _citations(links: list[WorkspaceEntryLink]) -> dict[str, dict[str, Any]]:
    cited: dict[str, dict[str, Any]] = {}
    for link in links:
        anchor, metadata = link.source_anchor or {}, link.link_metadata or {}
        ids = anchor.get("financial_transaction_ids")
        refs = anchor.get("financial_ref_ids")
        if not isinstance(ids, list):
            continue
        saved = metadata.get("transactions")
        by_id = {item.get("key"): item for item in saved if isinstance(item, dict)} if isinstance(saved, list) else {}
        for index, value in enumerate(ids):
            if isinstance(value, str) and value not in cited:
                ref = refs[index] if isinstance(refs, list) and index < len(refs) else None
                cited[value] = dict(ref_id=ref, saved=by_id.get(value))
    return cited


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def finding_evidence_changes(db: Session, *, case_id: UUID, entry_ids: list[str]) -> dict[str, Any]:
    wanted = list(dict.fromkeys(entry_ids))
    if len(wanted) > MAX_ENTRIES:
        raise EvidenceChangeError(f"{len(wanted)} findings were sent; one request takes at most {MAX_ENTRIES}.")
    links = db.scalars(select(WorkspaceEntryLink).join(
        WorkspaceEntry, WorkspaceEntry.id == WorkspaceEntryLink.entry_id).where(
        WorkspaceEntryLink.case_id == case_id, WorkspaceEntry.case_id == case_id,
        WorkspaceEntry.deleted_at.is_(None), WorkspaceEntryLink.entry_id.in_([UUID(v) for v in wanted]))).all()
    by_entry: dict[str, dict[str, dict[str, Any]]] = {value: {} for value in wanted}
    grouped: dict[str, list[WorkspaceEntryLink]] = {}
    for link in links:
        grouped.setdefault(str(link.entry_id), []).append(link)
    for entry_id, entry_links in grouped.items():
        by_entry[entry_id] = _citations(entry_links)
    ids = {value for cited in by_entry.values() for value in cited if _is_uuid(value)}
    rows = _load(db, case_id, ids) if ids else {}
    entries = {}
    for entry_id, cited in by_entry.items():
        changed, not_compared = [], 0
        for value, citation in cited.items():
            saved, row = citation["saved"], rows.get(value)
            if row is None:
                changed.append(dict(transaction_id=value, ref_id=citation["ref_id"], state="missing",
                                    current_id=None, changes=[]))
                continue
            current = _current(row, rows)
            state = None
            if current.ledger_status != "admitted":
                state = "set_aside"
            elif current.id != row.id:
                state = "corrected"
            changes = _differences(saved, current) if saved else []
            if saved is None:
                not_compared += 1
            if state or changes:
                changed.append(dict(transaction_id=value, ref_id=citation["ref_id"] or row.ref_id,
                                    state=state or "changed", current_id=str(current.id),
                                    currency=current.currency, changes=changes))
        entries[entry_id] = dict(cited=len(cited), not_compared=not_compared, changed=changed)
    return dict(case_id=str(case_id), entries=entries)
