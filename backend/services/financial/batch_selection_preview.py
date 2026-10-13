"""What the investigator should know about a statement selection before any batch starts.

Two facts, both from stored data (no PDF is read, nothing is written):

* open batches that already hold some of these files, so the investigator can
  continue that work instead of preparing the same statements again;
* files that are copies of statements already in Financial: the same bytes as
  another file in the case, or statements an earlier reading of this very file
  set aside as copies (validated against current inputs, exactly as a batch
  read validates them).

Nothing here removes or rejects a file. The investigator decides.
"""
from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item

OPEN_ITEM_STATES = ('ready', 'attention', 'pending_import')


def _active(file):
    metadata = file.metadata_ or {}
    visibility = metadata.get('financial_file_visibility')
    return not (isinstance(visibility, dict) and visibility.get('removed') is True) and not metadata.get('financial_import_removal')


def open_batches(session, case_id, selected):
    """Open batches sharing files with the selection, best match first.

    Open means not finished: a file still being read, or a statement still
    ready, needing attention or being saved (stored statuses; a hint, not an
    admission decision).
    """
    batches = [b for b in session.scalars(select(Batch).where(Batch.case_id == case_id, Batch.status != 'removed')
               .order_by(Batch.created_at.desc(), Batch.id).limit(200))
               if not any(f.get('standalone_import') for f in b.files)]
    overlapping = []
    for batch in batches:
        files = {f.get('file_id') for f in batch.files} | {f.get('source_id') for f in batch.files}
        shared = selected & files
        if shared:
            overlapping.append((batch, shared))
    if not overlapping:
        return []
    unfinished = dict(session.execute(select(Item.batch_id, func.count()).where(
        Item.batch_id.in_([b.id for b, _ in overlapping]), Item.status.in_(OPEN_ITEM_STATES)).group_by(Item.batch_id)).all())
    result = []
    for batch, shared in overlapping:
        reading = sum(f.get('status') not in ('checked', 'error') for f in batch.files)
        if not reading and not unfinished.get(batch.id):
            continue
        result.append(dict(id=str(batch.id), created_at=batch.created_at.isoformat(), status=batch.status,
            created_by=(batch.actor or {}).get('name', ''), file_count=len(batch.files),
            shared_files=len(shared), selected_files=len(selected),
            covers_selection=len(shared) == len(selected),
            other_files=sorted(selected - shared),
            unfinished_statements=unfinished.get(batch.id, 0), files_reading=reading))
    # Covers everything first, then most files shared; the query order keeps the most recent first.
    result.sort(key=lambda b: (not b['covers_selection'], -b['shared_files']))
    return result


def selection_copies(session, case_id, files):
    """Per selected file: copies of statements already in Financial, or of another selected file."""
    from services.financial.import_batches import stored_copy_dispositions
    by_id = {str(f.id): f for f in files}
    found = defaultdict(list)
    # Same bytes as another file in this case that is already in Financial
    # (prepared in a batch or saved), or as another file in this selection.
    hashes = {f.sha256 for f in files if f.sha256}
    if hashes:
        twins = [f for f in session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
                 EvidenceFile.sha256.in_(hashes))) if _active(f)]
        twin_ids = [f.id for f in twins if str(f.id) not in by_id]
        in_financial = set()
        if twin_ids:
            in_financial |= set(session.scalars(select(Item.file_id).join(Batch, Batch.id == Item.batch_id).where(
                Batch.case_id == case_id, Batch.status != 'removed', Item.file_id.in_(twin_ids),
                Item.status.notin_(('removed', 'superseded_reading'))).distinct()))
            in_financial |= set(session.scalars(select(FinancialSourceDocument.evidence_file_id).where(
                FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.evidence_file_id.in_(twin_ids),
                FinancialSourceDocument.status == 'admitted').distinct()))
        selected_order = sorted(files, key=lambda f: (f.original_filename, str(f.id)))
        for file in files:
            same = [t for t in twins if t.sha256 == file.sha256 and t.id != file.id]
            known = [t for t in same if t.id in in_financial]
            if known:
                found[str(file.id)].append(dict(kind='identical_bytes_in_financial',
                    retained=[dict(evidence_file_id=str(t.id), filename=t.original_filename) for t in known[:5]]))
                continue
            # Within the selection, the first file by name is the one kept.
            first = next(f for f in selected_order if f.sha256 == file.sha256)
            if first.id != file.id:
                found[str(file.id)].append(dict(kind='identical_bytes_in_selection',
                    retained=[dict(evidence_file_id=str(first.id), filename=first.original_filename)]))
    # Statements an earlier reading of this file set aside as copies, still current.
    latest = {}
    for item in session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(Batch.case_id == case_id,
            Batch.status != 'removed', Item.file_id.in_([f.id for f in files]),
            Item.status.notin_(('removed', 'superseded_reading', 'assigned'))).order_by(Item.updated_at.desc(), Item.id)):
        latest.setdefault((item.file_id, item.statement_key or ''), item)
    if latest:
        copies = stored_copy_dispositions(session, case_id, list(latest.values()))
        per_file = defaultdict(lambda: dict(statements=0, copies=0, retained={}))
        for (file_id, _), item in latest.items():
            entry = per_file[str(file_id)]
            entry['statements'] += 1
            disposition = copies.get(item.id)
            if disposition:
                entry['copies'] += 1
                retained = disposition.get('retained') or {}
                key = retained.get('evidence_file_id') or retained.get('filename')
                entry['retained'].setdefault(key, dict(evidence_file_id=retained.get('evidence_file_id'),
                    filename=retained.get('filename') or 'another statement'))
        for file_id, entry in per_file.items():
            if entry['copies']:
                found[file_id].append(dict(kind='statements_already_copies', statements=entry['statements'],
                    copies=entry['copies'], retained=list(entry['retained'].values())[:5]))
    return [dict(file_id=file_id, filename=by_id[file_id].original_filename, findings=findings)
            for file_id, findings in found.items()]


def selection_preview(session, *, case_id, file_ids):
    selected = {str(identifier) for identifier in file_ids}
    files = list(session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
        EvidenceFile.id.in_([UUID(identifier) for identifier in selected]))))
    if len(files) != len(selected):
        from services.financial.pdf_candidates import PdfMappingError
        raise PdfMappingError('A selected file is no longer available in this case. Refresh the selection.', 404)
    batches = open_batches(session, case_id, selected)
    return dict(case_id=str(case_id), selected_files=len(selected), open_batches=batches[:5],
        suggested_batch_id=batches[0]['id'] if batches else None, copies=selection_copies(session, case_id, files))
