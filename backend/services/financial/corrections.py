"""Append an amount correction and audit event in one transaction.

Original reading fields and source locators are retained. Repeated edits form a
supersession chain; reverting a value is another correction, never an overwrite.
Native mandatory control totals cannot be revalidated from a statement identity:
those documents receive a durable reservation pending native revalidation.
"""
import copy
import uuid
from dataclasses import fields
from sqlalchemy import select

from postgres.models.enums import AdjudicationDecision, AdjudicationSubject, TransactionDirection
from postgres.models.financial import FinancialTransaction, FinancialSourceDocument, FinancialStatementPeriod
from services.financial.correction_preview import CorrectionPreviewError, preview_amount_correction
from services.financial.decisions import Actor, record
from services.financial.documents import reclassify_after_reconciliation, document_reconciliation
from services.financial.reconcile import reconcile_period
from services.financial.references import RowReading, content_hash, ref_id


def correct_transaction(session, *, case_id, transaction_id, amount_minor, direction,
                        expected_revision, actor, reason):
    """Commit an exact replacement or roll back every effect, including grading."""
    try:
        if not isinstance(actor, Actor) or not isinstance(reason, str) or not reason.strip():
            raise CorrectionPreviewError("A named actor and a stated reason are required.")
        preview = preview_amount_correction(session, case_id=case_id, transaction_id=transaction_id,
                                            amount_minor=amount_minor, direction=direction)
        if preview["document_revision"] != expected_revision:
            raise CorrectionPreviewError("The document changed. Review the correction again.", 409)
        original = session.get(FinancialTransaction, transaction_id)
        document = session.get(FinancialSourceDocument, original.source_document_id)
        if not preview["verification"]["can_record"]:
            raise CorrectionPreviewError(preview["verification"]["reason"], 409)
        rows = list(session.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == document.id)))
        if any(r.proof_class != document.proof_class for r in rows):
            raise CorrectionPreviewError("Document and row proof classes disagree; correction refused.", 409)
        reading_fields = {f.name: getattr(original, f.name) for f in fields(RowReading)}
        reading_fields.update(amount_minor=amount_minor, direction=TransactionDirection(direction))
        reading = RowReading(**reading_fields)
        hashes = {r.content_hash for r in rows}
        # Occurrences include historical versions. This supports correcting back
        # to a previous value without deleting its original citation.
        occurrence = 0
        while True:
            digest = content_hash(reading, occurrence)
            reference = ref_id(document.sha256_at_ingestion, digest)
            if digest not in hashes and session.scalar(select(FinancialTransaction.id).where(
                    FinancialTransaction.case_id == case_id, FinancialTransaction.ref_id == reference)) is None:
                break
            occurrence += 1
        values = {prop.key: copy.deepcopy(getattr(original, prop.key))
                  for prop in FinancialTransaction.__mapper__.column_attrs
                  if prop.key not in {"id", "created_at", "updated_at"}}
        replacement_id = uuid.uuid4()
        values.update(id=replacement_id, amount_minor=amount_minor, direction=direction,
                      ref_id=reference, content_hash=digest, superseded_by_id=None)
        values["provenance"] = {**values["provenance"], "correction": {
            "previous_transaction_id": str(original.id), "previous_ref_id": original.ref_id,
            "occurrence": occurrence, "version": 1}}
        replacement = FinancialTransaction(**values)
        event = record(session, case_id=case_id, subject=original,
                       subject_type=AdjudicationSubject.transaction,
                       decision=AdjudicationDecision.correct_transaction, reason=reason, actor=actor,
                       before={"row": preview["original"], "replacement_id": None,
                               "original_status": original.ledger_status,
                               "original_quarantine_reason": original.quarantine_reason,
                               "reviewed_revision": expected_revision,
                               "running_balance_comparison": None,
                               "printed_total_comparison": None, "printed_total_error": None},
                       after={"row": {**preview["original"], **preview["proposed"],
                                       "key": str(replacement_id), "ref_id": reference},
                              "replacement_id": str(replacement_id),
                              "original_status": "superseded", "original_quarantine_reason": None,
                              "reviewed_revision": expected_revision,
                              "running_balance_comparison": preview["running_balances"],
                              "printed_total_comparison": preview["printed_totals"],
                              "printed_total_error": preview["printed_totals_error"]})
        session.add(replacement)
        session.flush()
        original.ledger_status = "superseded"
        original.quarantine_reason = None
        original.superseded_by_id = replacement_id
        session.flush()
        periods = list(session.scalars(select(FinancialStatementPeriod).where(
            FinancialStatementPeriod.source_document_id == document.id)))
        for period in periods:
            linked = session.scalars(select(FinancialTransaction).where(FinancialTransaction.statement_period_id == period.id)).all()
            if any(r.case_id != case_id or r.source_document_id != document.id or r.account_id != period.account_id for r in linked):
                raise CorrectionPreviewError("Statement row ownership is inconsistent.", 409)
            reconcile_period(session, period)
        reservations = preview["verification"]["reservations"]
        document.metadata_ = {**(document.metadata_ or {}), "admissibility_reservations": reservations}
        reclassify_after_reconciliation(session, document, document_reconciliation(session, document), reservations=reservations)
        session.flush()
        if document.proof_class != preview["verification"]["proposed_proof_class"]:
            raise CorrectionPreviewError("Verification changed during recording; nothing was committed.", 409)
        result = {"case_id": str(case_id), "transaction_id": str(transaction_id),
                  "replacement_id": str(replacement_id), "replacement_ref_id": reference,
                  "adjudication_id": str(event.id), "applied": True,
                  "proof_class": document.proof_class, "ledger_status": replacement.ledger_status,
                  "native_controls_rechecked": False}
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
