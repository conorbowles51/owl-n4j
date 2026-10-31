"""Financial's library contains explicit financial work in any source format.

Older work is recognised from its saved reviews, batches and imports. Reading
text/tables in the ordinary evidence pipeline is not financial enrolment. This
projection is read-only and never starts jobs or changes the underlying evidence.
"""
from datetime import datetime, timezone

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialStatementReviewDraft
from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services.financial.source_lineage import _cacheable, case_files, lineage_groups

SCHEMA = 'loupe.financial.file/1'


def mark_financial_workspace(file, *, user_id=None):
    """Retain explicit preparation intent even after a later ordinary AI run."""
    metadata = file.metadata_ or {}
    if (metadata.get('financial_workspace') or {}).get('schema') == SCHEMA:
        return
    file.metadata_ = {**metadata, 'financial_workspace': dict(
        schema=SCHEMA, selected_at=datetime.now(timezone.utc).isoformat(),
        selected_by=str(user_id) if user_id else None)}


def _pdf_review_ids(session, case_id, files):
    """Ids of the case's files last prepared in PDF review mode.

    Read as one JSON path from the database rather than by loading every
    file's profile snapshot (14 MB of the 26 MB of evidence rows on the largest
    case, measured 2026-10-30). Files that are this session's own unflushed
    objects are read from the objects, which is what the database would say
    once they are written.
    """
    if not _cacheable(session):
        return {file.id for file in files
                if (file.last_processed_profile_snapshot or {}).get('preparation_mode') == 'pdf_review'}
    mode = EvidenceFile.last_processed_profile_snapshot['preparation_mode'].as_string()
    return set(session.scalars(select(EvidenceFile.id).where(EvidenceFile.case_id == case_id, mode == 'pdf_review')))


def financial_file_ids(session, *, case_id):
    # The per-process copies of the case's rows (reused while each row's version
    # is unchanged), not every row loaded whole: measured 2026-10-30 on the
    # largest case, the whole-row load was 4.1 of the 4.3 s of 'who added this
    # file to Financial'.
    files = list(case_files(session, case_id).values())
    pdf_review = _pdf_review_ids(session, case_id, files)
    selected = set()
    for file in files:
        metadata = file.metadata_ or {}
        if (
            (metadata.get('financial_workspace') or {}).get('schema') == SCHEMA
            or file.id in pdf_review
            or any(metadata.get(key) for key in (
                'financial_review_progress', 'financial_review_history',
                'statement_version_request', 'financial_import_removal', 'financial_file_visibility',
            ))
        ):
            selected.add(str(file.id))

    # Keep historical imports, incomplete records and saved manual PDF reviews.
    # Intersecting with case-owned files below rejects foreign references.
    for model in (FinancialSourceDocument, FinancialCandidateMapping, FinancialStatementReviewDraft):
        selected.update(str(value) for value in session.scalars(
            select(model.evidence_file_id).where(model.case_id == case_id)))

    # A batch is explicit intent before its worker starts. Include both source
    # and prepared ids, even for failed/removed runs that remain in history.
    for entries in session.scalars(select(FinancialImportBatch.files).where(FinancialImportBatch.case_id == case_id)):
        for entry in entries or []:
            selected.update(str(entry[key]) for key in ('source_id', 'file_id') if entry.get(key))
    selected.update(str(value) for value in session.scalars(
        select(FinancialImportBatchItem.file_id).join(FinancialImportBatch,
            FinancialImportBatchItem.batch_id == FinancialImportBatch.id)
        .where(FinancialImportBatch.case_id == case_id)))

    from services.financial.payment_document_proposal import SCHEMA as DOCUMENT_REVIEW_SCHEMA
    selected.update(session.scalars(select(WorkspaceEntryLink.target_id).join(WorkspaceEntry,
        WorkspaceEntryLink.entry_id == WorkspaceEntry.id).where(
            WorkspaceEntry.case_id == case_id, WorkspaceEntryLink.case_id == case_id,
            WorkspaceEntryLink.target_type == 'evidence',
            WorkspaceEntryLink.link_metadata['schema'].as_string() == DOCUMENT_REVIEW_SCHEMA)))

    # Group only verified same-case, byte-identical reading lineage, never an
    # independently uploaded file with the same name or hash.
    return {file.id for versions in lineage_groups(files).values()
            if any(str(file.id) in selected for file in versions)
            for file in versions}
