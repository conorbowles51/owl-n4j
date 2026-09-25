"""Fresh, case-scoped duplicate candidates. No writes or automatic exclusion.

Stored fingerprints predate complete row coverage and may be absent or stale.
Recompute in memory so existing documents participate without a backfill write.
A comparison says what matches; persisted status says what is actually excluded.
"""

import re
import uuid
from collections import Counter

from sqlalchemy import func, select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialTransaction, FinancialStatementPeriod
from services.financial.duplicates import fingerprint_documents
from services.financial.duplicate_decisions import duplicate_revisions

MAX_COMPARISON_DOCUMENTS = 500
MAX_COMPARISON_ROWS = 50000
MAX_COMPARISON_PERIODS = 10000


class DuplicateQueryLimitError(Exception):
    """The complete candidate scan is too large for this synchronous read."""


def _statement_contexts(session, case_id, documents):
    """Describe registered periods, without inferring coverage from payments.

    These are the same period/account/source identities used by
    ledger_source.statement_source. The source endpoint remains responsible
    for verifying its evidence citation when an investigator opens it.
    """
    contexts = {document.id: [] for document in documents}
    if not documents:
        return contexts
    pairs = list(session.execute(select(FinancialStatementPeriod, FinancialAccount)
        .join(FinancialAccount, FinancialStatementPeriod.account_id == FinancialAccount.id)
        .where(FinancialStatementPeriod.case_id == case_id,
            FinancialAccount.case_id == case_id,
            FinancialStatementPeriod.source_document_id.in_(contexts))
        .order_by(FinancialStatementPeriod.period_start, FinancialStatementPeriod.period_end,
            FinancialStatementPeriod.account_id, FinancialStatementPeriod.id)))
    for period, account in pairs:
        contexts[period.source_document_id].append(dict(
            period_id=str(period.id), account_id=str(account.id),
            bank=account.institution_name, account_holder=account.holder_name,
            account_number=account.identifier_as_printed, currency=period.currency,
            period_start=period.period_start.isoformat() if period.period_start else None,
            period_end=period.period_end.isoformat() if period.period_end else None))
    # A single saved statement's edited header is more specific than a shared
    # account record. Preserve explicit blanks; do not substitute another
    # statement's holder. Multi-period documents keep each registered account.
    for document in documents:
        rows = contexts[document.id]
        if len(rows) != 1 or document.document_type != 'statement_review':
            continue
        metadata = document.metadata_ or {}
        request = metadata.get('statement_import_request')
        review = metadata.get('statement_details_review')
        details = review.get('details') if isinstance(review, dict) else None
        for source, target in (('institution', 'bank'), ('holder', 'account_holder'),
                               ('account_number', 'account_number')):
            for saved in (request, details):
                if isinstance(saved, dict) and source in saved:
                    value = saved[source]
                    rows[0][target] = value if isinstance(value, str) and value.strip() else None
    return contexts


def list_duplicate_candidates(session, case_id: uuid.UUID) -> dict:
    documents = list(session.scalars(
        select(FinancialSourceDocument)
        .where(FinancialSourceDocument.case_id == case_id)
        .order_by(FinancialSourceDocument.id)
        .limit(MAX_COMPARISON_DOCUMENTS + 1)
    ))
    if len(documents) > MAX_COMPARISON_DOCUMENTS:
        raise DuplicateQueryLimitError(
            f"This case exceeds the {MAX_COMPARISON_DOCUMENTS}-document comparison limit. "
            "No partial comparison has been returned."
        )
    row_count = session.scalar(select(func.count()).select_from(FinancialTransaction).where(
        FinancialTransaction.case_id == case_id))
    if row_count > MAX_COMPARISON_ROWS:
        raise DuplicateQueryLimitError('This case exceeds the50,000-reading comparison limit. No partial comparison was returned.')
    period_count = session.scalar(select(func.count()).select_from(FinancialStatementPeriod).where(
        FinancialStatementPeriod.case_id == case_id))
    if period_count > MAX_COMPARISON_PERIODS:
        raise DuplicateQueryLimitError('This case exceeds the10,000-period comparison limit. No partial comparison was returned.')
    eligible = [d for d in documents if d.status in ('admitted', 'superseded')]
    fingerprints, rows_by_document = fingerprint_documents(session, eligible)
    revisions = duplicate_revisions(session, eligible, fingerprints, rows_by_document)
    files = dict(session.execute(
        select(EvidenceFile.id, EvidenceFile.original_filename)
        .where(EvidenceFile.case_id == case_id)
        .where(EvidenceFile.id.in_([d.evidence_file_id for d in documents]))
    ).all())
    contexts = _statement_contexts(session, case_id, documents)
    groups = {}
    hash_groups = {}
    skipped = []
    compared = 0
    excluded_documents = []
    for document in documents:
        # Match the stored statement reference accepted by statement_source;
        # never manufacture a section reference from a filename or row date.
        statement_id = (document.metadata_ or {}).get('statement_import_statement_id')
        if not isinstance(statement_id, str) or re.fullmatch(r'[a-f0-9]{64}', statement_id) is None:
            statement_id = None
        view = {
            "document_id": str(document.id),
            "filename": files.get(document.evidence_file_id, "Source file unavailable"),
            "status": document.status,
            "superseded_by_id": str(document.superseded_by_id) if document.superseded_by_id else None,
            "evidence_file_id": str(document.evidence_file_id) if document.evidence_file_id in files else None,
            "statement_id": statement_id,
            "statement_context": contexts[document.id],
        }
        if document.status not in ("admitted", "superseded"):
            if document.sha256_at_ingestion:
                hash_groups.setdefault(document.sha256_at_ingestion, []).append((view.copy(), None))
            skipped.append({**view, "reason": "Document is held out or rejected."})
            continue
        view["revision"] = revisions[document.id]
        source_rows = rows_by_document.get(document.id, [])
        view["rows_by_status"] = dict(Counter(r.ledger_status for r in source_rows))
        if document.status == "superseded":
            excluded_documents.append(view.copy())
        fingerprint = fingerprints[document.id]
        view['source_transaction_id'] = str(min(source_rows, key=lambda r: (r.row_index, r.id)).id) if source_rows else None
        if document.sha256_at_ingestion:
            hash_groups.setdefault(document.sha256_at_ingestion, []).append((view.copy(), fingerprint.group_key))
        if fingerprint.group_key is None:
            skipped.append({**view, "reason": "No stored periods or transactions to compare."})
            continue
        view["reading_fingerprint"] = fingerprint.content_fingerprint
        compared += 1
        groups.setdefault(fingerprint.group_key, []).append((document, view, fingerprint))

    result = []
    for key, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        # An anchor for comparison, not an instruction about which file to keep.
        # Prefer an admitted document so supersession cannot nominate hidden rows.
        members.sort(key=lambda entry: (entry[0].status != "admitted", str(entry[0].id)))
        anchor, _, anchor_fingerprint = members[0]
        views = []
        for document, view, fingerprint in members:
            same_reading = fingerprint.content_fingerprint == anchor_fingerprint.content_fingerprint
            same_bytes = bool(document.sha256_at_ingestion) and document.sha256_at_ingestion == anchor.sha256_at_ingestion
            match = (
                "comparison_document" if document.id == anchor.id else
                "same_file_different_reading" if same_bytes and not same_reading else
                "identical_bytes" if same_bytes else
                "identical_reading" if same_reading else "shared_coverage"
            )
            views.append({**view, "match": match})
        result.append({"group_key": key, "members": views})
    return {
        "case_id": str(case_id), "documents": len(documents),
        "compared": compared, "skipped": skipped, "groups": result,
        "excluded_documents": excluded_documents,
        "stored_rows_in_case": row_count,
        "source_hash_groups": [dict(sha256_at_ingestion=digest,
            members=[view for view, _ in members],
            limitation="Matching recorded ingestion hashes with different or unavailable account/period coverage. This does not establish equal readings, fresh source-byte verification or permission to exclude either document.")
            for digest, members in sorted(hash_groups.items())
            if len(members) > 1 and (len({key for _, key in members}) > 1 or any(key is None for _, key in members))],
    }
