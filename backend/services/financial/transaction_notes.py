"""Capture current investigator notes linked to exported transaction readings."""
from sqlalchemy import select
from uuid import UUID
from postgres.models.financial import FinancialTransaction, FinancialSourceDocument
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services.financial.ledger_summary import LedgerSummaryError

MAX_NOTE_LINKS = 10000


def _reading_history(session, case_id, readings):
    """Resolve old citation ids to selected readings through verified chains."""
    rows = {reading['row']['key']: reading for reading in readings}
    aliases = {key: {key} for key in rows}
    files = {key: reading['source']['evidence_file_id'] for key, reading in rows.items()}
    identities = [UUID(key) for key in rows]
    nodes = {}
    for offset in range(0, len(identities), 400):
        for row in session.scalars(select(FinancialTransaction).where(FinancialTransaction.case_id == case_id,
                FinancialTransaction.id.in_(identities[offset:offset + 400]))):
            nodes[str(row.id)] = row
    frontier = list(nodes)
    parents = {}
    while frontier:
        found = []
        for offset in range(0, len(frontier), 400):
            found.extend(session.execute(select(FinancialTransaction, FinancialSourceDocument.evidence_file_id)
                .join(FinancialSourceDocument, FinancialTransaction.source_document_id == FinancialSourceDocument.id)
                .where(FinancialTransaction.case_id == case_id, FinancialSourceDocument.case_id == case_id,
                    FinancialTransaction.superseded_by_id.in_([UUID(key) for key in frontier[offset:offset + 400]]))).all())
        next_frontier = []
        for parent, file_id in found:
            child_key, key = str(parent.superseded_by_id), str(parent.id)
            child = nodes[child_key]
            if (child.provenance or {}).get('correction', {}).get('previous_transaction_id') != key:
                raise LedgerSummaryError('A payment citation has inconsistent correction history. Review its source before exporting.')
            if child_key in parents and parents[child_key] != key:
                raise LedgerSummaryError('A payment has more than one correction predecessor. Review its source history.')
            parents[child_key] = key
            files[key] = str(file_id)
            if key not in nodes:
                nodes[key] = parent
                next_frontier.append(key)
        if len(nodes) > MAX_NOTE_LINKS:
            raise LedgerSummaryError('Correction history exceeds the export limit. Narrow the export scope.')
        frontier = next_frontier
    for target in rows:
        visited, key = set(), target
        while key in parents:
            if key in visited:
                raise LedgerSummaryError('A payment correction chain contains a cycle. Review its history before exporting.')
            visited.add(key)
            key = parents[key]
            aliases.setdefault(key, set()).add(target)
    return aliases, files


def capture_transaction_notes(session, *, case_id, readings):
    rows = {reading['row']['key']: reading for reading in readings}
    aliases, source_files = _reading_history(session, case_id, readings)
    file_ids = {file_id for file_id in source_files.values() if file_id}
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
        cited = {identifier for identifier in ids if isinstance(identifier, str) and identifier in aliases}
        matched = sorted({current for identifier in cited for current in aliases[identifier]})
        if not matched:
            continue
        if any(source_files[identifier] != link.target_id for identifier in cited):
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
