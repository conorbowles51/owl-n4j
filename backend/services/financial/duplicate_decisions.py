"""Explicit, reversible duplicate decisions with exact row provenance.

The caller supplies the revision it reviewed. Documents, periods and rows are
locked before that revision and the pair's readings are checked again. The
service owns commit/rollback; a successful response means the event and state
were committed together. Legacy exclusions without row provenance cannot be
restored by this path.
"""
import hashlib
import json
import uuid

from sqlalchemy import select

from postgres.models.enums import AdjudicationDecision, AdjudicationSubject, ProofClass
from postgres.models.financial import (
    AdjudicationEvent, FinancialSourceDocument, FinancialStatementPeriod,
    FinancialTransaction,
)
from services.financial.proof_class import counts_toward_totals
from services.financial.decisions import Actor, record
from services.financial.duplicates import fingerprint_document


class DuplicateDecisionError(Exception):
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


def _latest(session, document):
    return session.scalar(select(AdjudicationEvent).where(
        AdjudicationEvent.case_id == document.case_id,
        AdjudicationEvent.subject_id == document.id,
        AdjudicationEvent.subject_type == "source_document",
    ).order_by(AdjudicationEvent.subject_sequence.desc()).limit(1))


def duplicate_revision(session, document):
    fingerprint = fingerprint_document(session, document)
    rows = list(session.execute(select(
        FinancialTransaction.id, FinancialTransaction.ledger_status,
        FinancialTransaction.superseded_by_id, FinancialTransaction.content_hash,
        FinancialTransaction.proof_class,
    ).where(FinancialTransaction.source_document_id == document.id)
      .order_by(FinancialTransaction.id)))
    latest = _latest(session, document)
    value = [str(document.id), document.status, str(document.superseded_by_id),
             document.duplicate_match_rung, document.duplicate_review_required, document.proof_class,
             fingerprint.content_fingerprint,
             latest.subject_sequence if latest else 0,
             [[str(item) for item in row] for row in rows]]
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def decide_duplicate(session, *, case_id, document_id, action, expected_revision,
                     actor, reason, primary_id=None, expected_primary_revision=None):
    """Commit one confirmed exclusion or exact reversal, or roll back everything."""
    try:
        return _decide(session, case_id=case_id, document_id=document_id,
                       action=action, expected_revision=expected_revision,
                       actor=actor, reason=reason, primary_id=primary_id,
                       expected_primary_revision=expected_primary_revision)
    except Exception:
        session.rollback()
        raise


def _decide(session, *, case_id, document_id, action, expected_revision,
            actor, reason, primary_id, expected_primary_revision):
    if not isinstance(actor, Actor) or not isinstance(reason, str) or not reason.strip():
        raise DuplicateDecisionError("A named actor and a stated reason are required.", 422)
    if action not in ("exclude", "restore"):
        raise DuplicateDecisionError("Unknown duplicate action.", 422)
    if action == "exclude" and (primary_id is None or primary_id == document_id):
        raise DuplicateDecisionError("Choose a different document to retain.", 422)
    if action == "restore" and primary_id is not None:
        raise DuplicateDecisionError("Restoration does not select another primary.", 422)
    ids = {document_id} | ({primary_id} if primary_id else set())
    documents = list(session.scalars(select(FinancialSourceDocument).where(
        FinancialSourceDocument.case_id == case_id,
        FinancialSourceDocument.id.in_(ids),
    ).order_by(FinancialSourceDocument.id).with_for_update()
      .execution_options(populate_existing=True)))
    if len(documents) != len(ids):
        raise DuplicateDecisionError("Document not found in this case.", 404)
    by_id = {d.id: d for d in documents}
    document = by_id[document_id]
    # Freeze the population and observations used for comparison. Future row
    # correction writers must follow the same document -> periods -> rows order.
    list(session.scalars(select(FinancialStatementPeriod).where(
        FinancialStatementPeriod.source_document_id.in_(ids)
    ).order_by(FinancialStatementPeriod.id).with_for_update()
      .execution_options(populate_existing=True)))
    rows = list(session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.source_document_id.in_(ids)
    ).order_by(FinancialTransaction.id).with_for_update()
      .execution_options(populate_existing=True)))
    if any(row.case_id != case_id for row in rows):
        raise DuplicateDecisionError("Inconsistent document ownership; nothing changed.")
    if duplicate_revision(session, document) != expected_revision:
        raise DuplicateDecisionError("The document changed. Refresh the comparison and review it again.")
    own_rows = [r for r in rows if r.source_document_id == document_id]
    before = {"status": document.status,
              "superseded_by_id": str(document.superseded_by_id) if document.superseded_by_id else None,
              "duplicate_match_rung": document.duplicate_match_rung,
              "duplicate_review_required": document.duplicate_review_required,
              "duplicate_review_version": 1, "rows": {},
              "reviewed_revision": expected_revision,
              "retained_revision": expected_primary_revision}
    after = dict(before)
    if action == "exclude":
        primary = by_id[primary_id]
        if duplicate_revision(session, primary) != expected_primary_revision:
            raise DuplicateDecisionError("The retained document changed. Refresh and review it again.")
        if document.status != "admitted" or primary.status != "admitted":
            raise DuplicateDecisionError("Both documents must still be admitted.")
        if document.superseded_by_id or primary.superseded_by_id:
            raise DuplicateDecisionError("An existing supersession must be reviewed first.")
        dependent = session.scalar(select(FinancialSourceDocument.id).where(
            FinancialSourceDocument.superseded_by_id == document_id
        ).limit(1))
        if dependent is not None:
            raise DuplicateDecisionError("Other documents depend on this primary. Restore them first.")
        source = fingerprint_document(session, document)
        retained = fingerprint_document(session, primary)
        if not source.content_fingerprint or source != retained:
            raise DuplicateDecisionError("The stored readings do not match; exclusion was refused.")
        # A retained copy with held/corrected rows is not equivalent for totals,
        # even when its full historical reading matches the excluded document.
        primary_rows = [r for r in rows if r.source_document_id == primary_id]
        if (not counts_toward_totals(ProofClass(primary.proof_class)) or
            any(not counts_toward_totals(ProofClass(r.proof_class)) for r in primary_rows)):
            raise DuplicateDecisionError("The retained copy is not eligible for ledger totals.")
        if any(r.ledger_status != "admitted" or r.superseded_by_id for r in primary_rows):
            raise DuplicateDecisionError("The retained copy has rows set aside or corrected; review them first.")
        changed = [r for r in own_rows if r.ledger_status == "admitted"]
        if any(r.superseded_by_id for r in changed):
            raise DuplicateDecisionError("A corrected row cannot be excluded as an admitted row.")
        after.update(status="superseded", superseded_by_id=str(primary_id),
                     duplicate_match_rung=0 if document.sha256_at_ingestion == primary.sha256_at_ingestion else 1,
                     duplicate_review_required=False)
        target_status = "superseded"
        decision = AdjudicationDecision.supersede_duplicate
    else:
        latest = _latest(session, document)
        if (document.status != "superseded" or latest is None or
            latest.decision != "supersede_duplicate" or not latest.after or
            latest.after.get("duplicate_review_version") != 1):
            raise DuplicateDecisionError("This exclusion has no current reversible row record; restoration was refused.")
        recorded = latest.after.get("rows")
        original = (latest.before or {}).get("rows")
        if (not isinstance(recorded, dict) or not isinstance(original, dict) or
            recorded.keys() != original.keys() or
            any(value != "superseded" for value in recorded.values()) or
            any(value != "admitted" for value in original.values())):
            raise DuplicateDecisionError("The exclusion row record is incomplete; restoration was refused.")
        by_row = {str(r.id): r for r in own_rows}
        if any(key not in by_row for key in recorded):
            raise DuplicateDecisionError("Excluded rows changed or disappeared; review is required.")
        changed = [by_row[key] for key in recorded]
        if any(r.ledger_status != "superseded" or r.superseded_by_id for r in changed):
            raise DuplicateDecisionError("A row changed after exclusion; restoration cannot overwrite that decision.")
        if latest.after.get("superseded_by_id") != str(document.superseded_by_id):
            raise DuplicateDecisionError("The exclusion target changed; review is required.")
        after.update(status="admitted", superseded_by_id=None,
                     duplicate_match_rung=None, duplicate_review_required=False)
        target_status = "admitted"
        decision = AdjudicationDecision.restore_document
    before["rows"] = {str(r.id): r.ledger_status for r in changed}
    after["rows"] = {str(r.id): target_status for r in changed}
    event = record(session, case_id=case_id, subject=document,
                   subject_type=AdjudicationSubject.source_document,
                   decision=decision, reason=reason, actor=actor,
                   before=before, after=after)
    document.status = after["status"]
    document.superseded_by_id = uuid.UUID(after["superseded_by_id"]) if after["superseded_by_id"] else None
    document.duplicate_match_rung = after["duplicate_match_rung"]
    document.duplicate_review_required = after["duplicate_review_required"]
    for row in changed:
        row.ledger_status = target_status
    response = {"case_id": str(case_id), "document_id": str(document_id),
                "action": action, "applied": True, "changed_rows": len(changed),
                "adjudication_id": str(event.id)}
    session.commit()
    return response
