"""Read-only comparison between two explicitly authorized cases.

Callers must authorize both cases before invoking this service. No cross-case
exclusion is offered: a copy may legitimately be evidence in each case.
"""
from sqlalchemy import select, func
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction, FinancialStatementPeriod
from services.financial.duplicate_query import DuplicateQueryLimitError
from services.financial.duplicates import fingerprint_documents

MAX_DOCUMENTS = 500
MAX_ROWS = 50000
MAX_MATCHES = 1000


def compare_case_documents(session, case_id, comparison_case_id):
    if case_id == comparison_case_id:
        raise DuplicateQueryLimitError('Choose a different case for this comparison.')
    cases = (case_id, comparison_case_id)
    documents = {}
    for case in cases:
        items = list(session.scalars(select(FinancialSourceDocument).where(
            FinancialSourceDocument.case_id == case).order_by(FinancialSourceDocument.id).limit(MAX_DOCUMENTS + 1)))
        if len(items) > MAX_DOCUMENTS:
            raise DuplicateQueryLimitError('A selected case exceeds 500 financial documents; no partial comparison was returned.')
        documents[case] = items
    row_count = session.scalar(select(func.count()).select_from(FinancialTransaction).where(FinancialTransaction.case_id.in_(cases)))
    if row_count > MAX_ROWS:
        raise DuplicateQueryLimitError('The selected cases exceed 50,000 stored readings; no partial comparison was returned.')
    period_count = session.scalar(select(func.count()).select_from(FinancialStatementPeriod).where(FinancialStatementPeriod.case_id.in_(cases)))
    if period_count > 10000:
        raise DuplicateQueryLimitError('The selected cases exceed10,000statement periods; no partial comparison was returned.')
    eligible = [d for items in documents.values() for d in items if d.status in ('admitted', 'superseded')]
    fingerprints, _rows = fingerprint_documents(session, eligible)
    files = dict(session.execute(select(EvidenceFile.id, EvidenceFile.original_filename).where(EvidenceFile.case_id.in_(cases), EvidenceFile.id.in_([d.evidence_file_id for items in documents.values() for d in items]))).all())
    prepared = {}
    skipped = []
    for case, items in documents.items():
        prepared[case] = []
        for document in items:
            view = dict(case_id=str(case), document_id=str(document.id), filename=files.get(document.evidence_file_id, 'Source file unavailable'), status=document.status)
            if document.status not in ('admitted', 'superseded'):
                skipped.append({**view, 'reason':'Document is held out or rejected.'})
                continue
            fingerprint = fingerprints[document.id]
            prepared[case].append((document, view, fingerprint))
    matches = []
    for left, left_view, left_fp in prepared[case_id]:
        for right, right_view, right_fp in prepared[comparison_case_id]:
            same_bytes = bool(left.sha256_at_ingestion) and left.sha256_at_ingestion == right.sha256_at_ingestion
            same_reading = bool(left_fp.group_key) and left_fp.group_key == right_fp.group_key and left_fp.content_fingerprint == right_fp.content_fingerprint
            if same_bytes or same_reading:
                matches.append(dict(left=left_view, right=right_view, matching_ingestion_hash=same_bytes, matching_stored_reading=same_reading))
                if len(matches) > MAX_MATCHES:
                    raise DuplicateQueryLimitError('More than 1,000 cross-case matches; no partial comparison was returned.')
    return dict(case_id=str(case_id), comparison_case_id=str(comparison_case_id), applied=False,
        documents={str(case):len(items) for case,items in documents.items()}, compared={str(case):len(items) for case,items in prepared.items()},
        stored_rows_checked=row_count, skipped=skipped, matches=matches,
        limitation='Matches compare ingestion hashes or stored readings with matching recorded account/period identity. Ingestion hashes are not a fresh verification of current file bytes. No match does not establish different underlying transactions. Missing or differently recorded account identities can prevent reading matches. Documents remain independent evidence in each case; no exclusion or totals change is made.')
