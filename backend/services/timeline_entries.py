"""Investigator-selected financial evidence in the shared case Timeline.

Snapshots retain the as-added evidence. Current readings are resolved on every
read; corrections keep the same event key and removed sources remain labelled.
"""
import hashlib
import json
from datetime import date
from typing import Literal
from uuid import UUID, NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field
from sqlalchemy import select, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from postgres.models.case import Case
from postgres.models.financial import FinancialTransaction, FinancialSourceDocument
from postgres.models.timeline_entry import TimelineEntry
from postgres.models.workspace_entry import WorkspaceEntry
from postgres.models.financial_money_trails import FinancialMoneyTrail
from services.financial.money import Money
from services.financial.transaction_query import to_view

PREFIX = "timeline-entry:"


class TimelineAddition(BaseModel):
    source_kind: Literal["transaction", "workspace_entry", "money_trail"]
    source_ids: list[UUID] = Field(min_length=1, max_length=5000)
    event_date: date | None = None
    expected_revision: str | None = None


def _key(case_id, kind, source_id):
    return PREFIX + str(uuid5(NAMESPACE_URL, f"loupe:{case_id}:{kind}:{source_id}"))


def _load_sources(db, case_id, kind, ids):
    if not ids: return {}
    if kind == "transaction":
        query = select(FinancialTransaction).where(FinancialTransaction.case_id == case_id, FinancialTransaction.id.in_(ids)).options(
            joinedload(FinancialTransaction.account), joinedload(FinancialTransaction.source_document).joinedload(FinancialSourceDocument.evidence_file))
    elif kind == "money_trail":
        query = select(FinancialMoneyTrail).where(FinancialMoneyTrail.case_id == case_id, FinancialMoneyTrail.id.in_(ids))
    else:
        query = select(WorkspaceEntry).where(WorkspaceEntry.case_id == case_id, WorkspaceEntry.id.in_(ids)).options(selectinload(WorkspaceEntry.links))
    return {row.id: row for row in db.scalars(query)}


def _transaction(db, case_id, id):
    row = db.get(FinancialTransaction, id)
    return row if row and row.case_id == case_id else None


def _root(db, row):
    seen = set()
    while row.id not in seen:
        seen.add(row.id)
        previous = (row.provenance or {}).get("correction", {}).get("previous_transaction_id")
        if not previous:
            return row.id
        parent = _transaction(db, row.case_id, UUID(previous))
        if not parent or parent.superseded_by_id != row.id:
            break
        row = parent
    raise ValueError("The payment's correction history could not be resolved. Refresh its details.")


def _current(db, row):
    seen = set()
    while row and row.superseded_by_id and row.id not in seen:
        seen.add(row.id)
        replacement = _transaction(db, row.case_id, row.superseded_by_id)
        if not replacement or (replacement.provenance or {}).get("correction", {}).get("previous_transaction_id") != str(row.id):
            break
        row = replacement
    return row


def _payment_event(row, key):
    view = to_view(row, account=row.account)
    # Statement-end ordering placeholders are never dates for timeline events.
    dated = next(((getattr(row, field), label) for field, label in (
        ("transaction_date", "Transaction date"), ("posted_date", "Posted date"),
        ("value_date", "Value date"), ("effective_date", "Effective date")) if getattr(row, field)), None)
    if not dated or (row.provenance or {}).get("date_basis") == "statement_end_ordering_only":
        return None
    filename = row.source_document.evidence_file.original_filename
    locator = view.locator or {}
    page = locator.get("page")
    source = f"{filename} · {row.ref_id}" + (f" · page {page}" if page else "")
    def party(field):
        name = getattr(view, field) or "Not identified"
        if view.label_sources.get(field, {}).get("source") == "description":
            return f"{name} (suggested from description)"
        return name

    direction = "Card credit" if view.account_type == "credit_card" and row.direction == "credit" else "Card charge" if view.account_type == "credit_card" else "Money in" if row.direction == "credit" else "Money out"
    return dict(key=key, name=row.description or row.ref_id, type="Transaction", date=dated[0].isoformat(), time=None,
        amount=f"{Money(row.amount_minor, row.currency).format()} · {direction}",
        summary=f"From: {party('from_name')} → To: {party('to_name')}. {view.account_label or 'Account not named'}. {source}",
        notes=None, connections=[dict(key=f"financial-account:{row.account_id}", name=view.account_label or "Unnamed account", type="FinancialAccount", relationship="ACCOUNT", direction="incoming" if row.direction == "debit" else "outgoing")], source_references=[source],
        source=dict(kind="transaction", id=str(row.id), date_basis=dated[1], label=source, state="current"))


def _finding_event(entry, key, event_date):
    tags = entry.tags or []
    kind = "Observation" if "financial-entry-observation" in tags or ("financial-observation" not in tags and "financial-conclusion" not in tags and "financial-entry-finding" not in tags) else "Finding"
    return dict(key=key, name=entry.title or f"Untitled {kind.lower()}", type=kind,
        date=event_date, time=None, amount=None, summary=entry.body, notes=None, connections=[],
        source_references=list(dict.fromkeys(link.target_label for link in entry.links if link.target_label)),
        source=dict(kind="workspace_entry", id=str(entry.id), date_basis="Event date chosen by investigator", label=entry.title or kind, state="current"))


def _transfer_event(db, record, key):
    from services.financial.money_trails import trail_view
    view = trail_view(db, record)
    if not record.active or record.kind != 'transfer' or view['status'] != 'current':
        raise ValueError('Review the current transfer sources before adding this movement to Timeline.')
    payments = [_transaction(db, record.case_id, UUID(p['key'])) for p in record.details['payments']]
    events = [_payment_event(p, key) for p in payments]
    if any(e is None for e in events):
        return None
    debit = next((i for i,p in enumerate(payments) if p.direction == 'debit'), 0)
    event = dict(events[debit])
    event.update(type='Transfer', name='Reviewed account transfer',
        summary='One movement supported by the linked statement entries. '+record.details['input']['reason']+'\n\n'+'\n'.join(e['summary'] for e in events)+'\n'+'\n'.join(record.details['warnings']),
        amount=' → '.join(dict.fromkeys(Money(p.amount_minor,p.currency).format() for p in payments)),
        source_references=list(dict.fromkeys(s for e in events for s in e['source_references'])),
        connections=[c for e in events for c in e['connections']],
        source=dict(kind='money_trail',id=str(record.id),date_basis='Sending entry date; receiving entry retains its own date',label='Reviewed transfer and both statements',state='current'),
        transfer_posting_roots=[str(_root(db,p)) for p in payments], trail_revision=record.revision)
    return event


def preview_addition(db: Session, *, case_id: UUID, request: TimelineAddition):
    ids = list(dict.fromkeys(request.source_ids))
    if request.source_kind == "workspace_entry" and not request.event_date:
        raise ValueError("Choose the event date for this finding or observation.")
    sources = _load_sources(db, case_id, request.source_kind, ids)
    existing_by_id = {entry.id: entry for entry in db.scalars(select(TimelineEntry).where(TimelineEntry.case_id == case_id))}
    combined = {root:entry for entry in existing_by_id.values() if entry.source_kind == 'money_trail'
                for root in entry.event_snapshot.get('transfer_posting_roots',[])}
    rows = []
    for id in ids:
        if request.source_kind == "transaction":
            row = sources.get(id)
            if not row or row.ledger_status != "admitted" or row.superseded_by_id or row.source_document.status != "admitted":
                raise ValueError("A selected payment changed or was removed. Refresh Transactions and select it again.")
            source_id = _root(db, row)
            key = _key(case_id, request.source_kind, source_id)
            event = _payment_event(row, key)
            title = row.description or row.ref_id
        elif request.source_kind == 'money_trail':
            record = sources.get(id)
            if not record: raise ValueError('The transfer is not available in this case.')
            source_id = id
            key = _key(case_id, request.source_kind, source_id)
            event = _transfer_event(db,record,key)
            title = 'Reviewed account transfer (both statement entries)'
        else:
            entry = sources.get(id)
            if not entry or entry.case_id != case_id or entry.deleted_at or "financial" not in entry.tags or "financial-report" in entry.tags:
                raise ValueError("This finding or observation is no longer available in this case. Refresh the list.")
            source_id = id
            key = _key(case_id, request.source_kind, source_id)
            event = _finding_event(entry, key, request.event_date.isoformat())
            title = event["name"]
        existing = existing_by_id.get(UUID(key[len(PREFIX):]))
        if request.source_kind == 'transaction' and str(source_id) in combined:
            existing = combined[str(source_id)]
        status = "already_added" if existing else "ready" if event else "undated"
        # Adding an existing finding does not silently change its chosen date.
        if existing:
            event = resolve_entry(db, existing)
        rows.append(dict(source_id=str(source_id), name=title, status=status, event=event))
    revision = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return dict(case_id=str(case_id), rows=rows, revision=revision,
        ready=sum(row["status"] == "ready" for row in rows),
        already_added=sum(row["status"] == "already_added" for row in rows),
        undated=sum(row["status"] == "undated" for row in rows))


def save_addition(db: Session, *, case_id: UUID, request: TimelineAddition, actor: str):
    try:
        # Serialize additions to this case so duplicate clicks cannot create two events.
        db.execute(select(Case.id).where(Case.id == case_id).with_for_update()).scalar_one()
        if request.source_kind == "transaction":
            db.execute(select(FinancialTransaction).where(FinancialTransaction.case_id == case_id,
                FinancialTransaction.id.in_(request.source_ids)).order_by(FinancialTransaction.id).with_for_update().execution_options(populate_existing=True)).scalars().all()
        elif request.source_kind == 'money_trail':
            db.execute(select(FinancialMoneyTrail).where(FinancialMoneyTrail.case_id == case_id,
                FinancialMoneyTrail.id.in_(request.source_ids)).with_for_update().execution_options(populate_existing=True)).scalars().all()
        else:
            db.execute(select(WorkspaceEntry).where(WorkspaceEntry.case_id == case_id,
                WorkspaceEntry.id.in_(request.source_ids)).with_for_update().execution_options(populate_existing=True)).scalars().all()
        preview = preview_addition(db, case_id=case_id, request=request)
        if preview["ready"] and request.expected_revision != preview["revision"]:
            raise ValueError("The selection changed since review. Refresh the preview before adding it.")
        keys = []
        for row in preview["rows"]:
            if row["event"]:
                keys.append(row["event"]["key"])
            if row["status"] == "ready":
                db.add(TimelineEntry(id=UUID(row["event"]["key"][len(PREFIX):]), case_id=case_id,
                    source_kind=request.source_kind, source_id=UUID(row["source_id"]),
                    event_snapshot=row["event"], added_by=actor))
        db.commit()
        return dict(case_id=str(case_id), added=preview["ready"], already_added=preview["already_added"], undated=preview["undated"], event_keys=keys)
    except Exception:
        db.rollback()
        raise


def resolve_entry(db, entry):
    snapshot = dict(entry.event_snapshot)
    event = None
    if entry.source_kind == "transaction":
        current = _current(db, _transaction(db, entry.case_id, entry.source_id))
        if current and current.ledger_status == "admitted" and current.source_document.status == "admitted":
            event = _payment_event(current, snapshot["key"])
    elif entry.source_kind == 'money_trail':
        current = db.get(FinancialMoneyTrail, entry.source_id)
        if current and current.case_id == entry.case_id:
            try: event = _transfer_event(db,current,snapshot['key'])
            except ValueError: pass
        if event and event.get('trail_revision') != snapshot.get('trail_revision'):
            # A saved chronology captures the interpretation the investigator added.
            event = None
    else:
        current = db.get(WorkspaceEntry, entry.source_id)
        if current and current.case_id == entry.case_id and not current.deleted_at:
            event = _finding_event(current, snapshot["key"], snapshot["date"])
    if event:
        return event
    snapshot["source"] = {**snapshot["source"], "state": "snapshot"}
    snapshot["summary"] = "Saved Timeline copy: the source was removed, excluded or no longer has a usable date. " + (snapshot.get("summary") or "")
    return snapshot


def list_entries(db, *, case_id, event_keys=None, offset=0, limit=2000):
    query = select(TimelineEntry).where(TimelineEntry.case_id == case_id)
    if event_keys is None:
        combined = {UUID(root) for snapshot in db.scalars(select(TimelineEntry.event_snapshot).where(
            TimelineEntry.case_id == case_id, TimelineEntry.source_kind == 'money_trail'))
            for root in snapshot.get('transfer_posting_roots',[])}
        if combined:
            query = query.where(or_(TimelineEntry.source_kind != 'transaction', TimelineEntry.source_id.not_in(combined)))
    if event_keys is not None:
        ids = []
        for key in event_keys:
            if key.startswith(PREFIX):
                try: ids.append(UUID(key[len(PREFIX):]))
                except ValueError: pass
        if not ids: return []
        query = query.where(TimelineEntry.id.in_(ids))
    entries = list(db.scalars(query.order_by(TimelineEntry.id).offset(offset).limit(limit)))
    # Retain these maps while resolving so SQLAlchemy's identity map supplies the
    # source records instead of issuing one query per event in a large import.
    sources = [_load_sources(db, case_id, kind, [entry.source_id for entry in entries if entry.source_kind == kind])
               for kind in ("transaction", "workspace_entry", "money_trail")]
    events = [resolve_entry(db, entry) for entry in entries]
    del sources
    return events
