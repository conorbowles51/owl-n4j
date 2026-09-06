"""Fresh, case-scoped duplicate candidates. No writes or automatic exclusion.

Stored fingerprints predate complete row coverage and may be absent or stale.
Recompute in memory so existing documents participate without a backfill write.
A comparison says what matches; persisted status says what is actually excluded.
"""

import uuid

from sqlalchemy import func, select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from services.financial.duplicates import fingerprint_document
from services.financial.duplicate_decisions import duplicate_revision

MAX_COMPARISON_DOCUMENTS = 500


class DuplicateQueryLimitError(Exception):
    """The complete candidate scan is too large for this synchronous read."""


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
    files = dict(session.execute(
        select(EvidenceFile.id, EvidenceFile.original_filename)
        .where(EvidenceFile.case_id == case_id)
        .where(EvidenceFile.id.in_([d.evidence_file_id for d in documents]))
    ).all())
    groups = {}
    skipped = []
    compared = 0
    excluded_documents = []
    for document in documents:
        view = {
            "document_id": str(document.id),
            "filename": files.get(document.evidence_file_id, "Source file unavailable"),
            "status": document.status,
            "superseded_by_id": str(document.superseded_by_id) if document.superseded_by_id else None,
        }
        if document.status not in ("admitted", "superseded"):
            skipped.append({**view, "reason": "Document is held out or rejected."})
            continue
        view["revision"] = duplicate_revision(session, document)
        if document.status == "superseded":
            excluded_documents.append(view.copy())
        fingerprint = fingerprint_document(session, document)
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
            counts = dict(session.execute(
                select(FinancialTransaction.ledger_status, func.count())
                .where(
                    FinancialTransaction.case_id == case_id,
                    FinancialTransaction.source_document_id == document.id,
                )
                .group_by(FinancialTransaction.ledger_status)
            ).all())
            views.append({**view, "match": match, "rows_by_status": dict(counts)})
        result.append({"group_key": key, "members": views})
    return {
        "case_id": str(case_id), "documents": len(documents),
        "compared": compared, "skipped": skipped, "groups": result,
        "excluded_documents": excluded_documents,
    }
