"""Bounded duplicate-decision freshness checks without reconstructing statements."""
from collections import defaultdict
from copy import deepcopy
from uuid import UUID

from sqlalchemy import String, cast, func, select

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceTableGeometry
from postgres.models.financial import FinancialSourceDocument
from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
from services.financial.pdf_candidates import _digest


def _uuid(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def load_projection_context(session, case_id, files):
    """Bulk scalar fingerprints; PostgreSQL hashes geometry inside the database."""
    from services.financial.statement_import import VERSION
    files = {str(file.id): file for file in files}
    ids = [file.id for file in files.values()]
    texts = {str(row.evidence_file_id): [row.content_sha256, str(row.engine_job_id), str(row.extracted_at)]
             for row in session.execute(select(EvidenceDocumentText.evidence_file_id,
                 EvidenceDocumentText.content_sha256, EvidenceDocumentText.engine_job_id,
                 EvidenceDocumentText.extracted_at).where(EvidenceDocumentText.evidence_file_id.in_(ids)))} if ids else {}
    geometry = defaultdict(list)
    postgres = session.get_bind().dialect.name == 'postgresql'
    fingerprint = func.md5(cast(EvidenceTableGeometry.payload, String)) if postgres else EvidenceTableGeometry.payload
    if ids:
        for file_id, page, job, extracted, value in session.execute(select(
                EvidenceTableGeometry.evidence_file_id, EvidenceTableGeometry.page_number,
                EvidenceTableGeometry.engine_job_id, EvidenceTableGeometry.extracted_at, fingerprint)
                .where(EvidenceTableGeometry.evidence_file_id.in_(ids)).order_by(
                    EvidenceTableGeometry.evidence_file_id, EvidenceTableGeometry.page_number)):
            geometry[str(file_id)].append([page, str(job), str(extracted), value if postgres else _digest(value)])
    drafts = defaultdict(list)
    if ids:
        for file_id, key, request in session.execute(select(FinancialImportBatchItem.file_id,
                FinancialImportBatchItem.statement_key, FinancialImportBatchItem.review_request)
                .join(FinancialImportBatch, FinancialImportBatch.id == FinancialImportBatchItem.batch_id)
                .where(FinancialImportBatch.case_id == case_id, FinancialImportBatch.status != 'removed',
                    FinancialImportBatchItem.file_id.in_(ids),
                    FinancialImportBatchItem.status.notin_(('removed', 'superseded_reading')),
                    FinancialImportBatchItem.review_request.is_not(None))):
            if request is not None:
                drafts[(str(file_id), key)].append(_digest(request))
    guards = {}
    for identifier, file in files.items():
        metadata = file.metadata_ or {}
        guards[identifier] = _digest(dict(version=VERSION, sha256=file.sha256,
            status=file.status, job=file.engine_job_id, text=texts.get(identifier),
            geometry=geometry[identifier], reading_metadata={key: value for key, value in metadata.items()
                if key.startswith('statement_')}))
    sources = {}
    source_fingerprint = func.md5(cast(FinancialSourceDocument.metadata_, String)) if postgres else FinancialSourceDocument.metadata_
    if ids:
        for identifier, status, value, removed in session.execute(select(FinancialSourceDocument.id,
                FinancialSourceDocument.status, source_fingerprint,
                FinancialSourceDocument.metadata_['financial_import_removal'].as_string())
                .where(FinancialSourceDocument.case_id == case_id,
                    FinancialSourceDocument.evidence_file_id.in_(ids))):
            sources[str(identifier)] = dict(status=status, fingerprint=value if postgres else _digest(value), removed=bool(removed))
    return dict(files=files, guards=guards, drafts=drafts, sources=sources)


def _period_guard(context, file_id, statement_id):
    file = context['files'].get(file_id)
    if file is None:
        return None
    saved = (file.metadata_ or {}).get('financial_review_progress', {}).get(statement_id or '')
    return dict(reading=context['guards'][file_id], shared_review=_digest(saved),
        batch_reviews=sorted(set(context['drafts'][(file_id, statement_id or '')])))


def projection_guard(context, file, statement_id, decision):
    retained = decision.get('retained') or {}
    retained_id = retained.get('evidence_file_id')
    source = context['sources'].get(retained.get('source_document_id'))
    return dict(own=_period_guard(context, str(file.id), statement_id),
        retained=_period_guard(context, retained_id, retained.get('statement_id')) if retained_id else None,
        retained_source=_digest(source) if source else None)


def capture_projection_guard(session, file, statement_id, decision):
    retained_id = _uuid((decision.get('retained') or {}).get('evidence_file_id'))
    ids = {file.id} | ({retained_id} if retained_id else set())
    files = list(session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == file.case_id,
        EvidenceFile.id.in_(ids))))
    return projection_guard(load_projection_context(session, file.case_id, files), file, statement_id, decision)


def cached_disposition(context, file, statement_id, *, reading_revision=None):
    previous = (file.metadata_ or {}).get('financial_duplicate_dispositions', {}).get(statement_id or '')
    if not previous:
        return None
    result = deepcopy(previous)
    result.pop('history', None)
    valid = bool(previous.get('projection_guard') and previous['projection_guard'] ==
                 projection_guard(context, file, statement_id, previous))
    if reading_revision and previous.get('reading_revision') != reading_revision:
        valid = False
    retained = previous.get('retained') or {}
    if previous.get('status') == 'ignored':
        target = context['files'].get(retained.get('evidence_file_id'))
        target_metadata = (target.metadata_ or {}) if target else {}
        valid = valid and bool(target) and not target_metadata.get('financial_file_visibility', {}).get('removed')
        valid = valid and not target_metadata.get('financial_import_removal')
        target_decision = target_metadata.get('financial_duplicate_dispositions', {}).get(retained.get('statement_id') or '')
        if target_decision and target_decision.get('status') == 'ignored':
            valid = False
        if retained.get('source_document_id'):
            source = context['sources'].get(retained['source_document_id'])
            valid = valid and bool(source and source['status'] == 'admitted' and not source['removed'])
    result['current'] = bool(valid)
    if not valid:
        result.update(status='needs_comparison', label='Compare this statement',
            reason='The reading, saved review or retained source changed. Check these statements again.')
    result.pop('projection_guard', None)
    return result
