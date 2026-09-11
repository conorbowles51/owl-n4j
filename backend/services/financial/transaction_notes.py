"""Capture current investigator notes linked to exported transaction readings."""
from sqlalchemy import select
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services.financial.ledger_summary import LedgerSummaryError

MAX_NOTE_LINKS = 10000


def capture_transaction_notes(session, *, case_id, readings):
    rows = {reading['row']['key']: reading for reading in readings}
    file_ids = {reading['source']['evidence_file_id'] for reading in readings if reading['source']['evidence_file_id']}
    if not file_ids:
        return []
    pairs = session.execute(select(WorkspaceEntry, WorkspaceEntryLink).join(
        WorkspaceEntryLink, WorkspaceEntryLink.entry_id == WorkspaceEntry.id).where(
        WorkspaceEntry.case_id == case_id, WorkspaceEntry.deleted_at.is_(None),
        WorkspaceEntryLink.case_id == case_id, WorkspaceEntryLink.target_type == 'evidence',
        WorkspaceEntryLink.target_id.in_(file_ids)).order_by(WorkspaceEntry.id, WorkspaceEntryLink.id)
        .limit(MAX_NOTE_LINKS + 1)).all()
    if len(pairs) > MAX_NOTE_LINKS:
        raise LedgerSummaryError('Linked investigation notes exceed the export limit. Narrow the export scope.')
    notes = {}
    for entry, link in pairs:
        ids = (link.source_anchor or {}).get('financial_transaction_ids')
        if not isinstance(ids, list):
            continue
        matched = sorted({identifier for identifier in ids if isinstance(identifier, str) and identifier in rows})
        if not matched:
            continue
        if any(rows[identifier]['source']['evidence_file_id'] != link.target_id for identifier in matched):
            raise LedgerSummaryError('An investigation note points to a different transaction source. Correct the Workspace link before exporting.')
        note = notes.setdefault(str(entry.id), dict(id=str(entry.id), case_id=str(case_id),
            entry_type=entry.entry_type, title=entry.title, body=entry.body, version=entry.version,
            review_state=entry.review_state, author_name=entry.author_name, author_email=entry.author_email,
            updated_at=entry.updated_at.isoformat() if entry.updated_at else None, links=[]))
        note['links'].append(dict(evidence_file_id=link.target_id, filename=link.target_label,
            transactions=[dict(transaction_id=identifier, ref_id=rows[identifier]['row']['ref_id'],
                               ledger_status=rows[identifier]['row']['ledger_status']) for identifier in matched],
            source_anchor=link.source_anchor))
    return list(notes.values())
