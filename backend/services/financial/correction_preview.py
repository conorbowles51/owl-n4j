"""Read-only amount correction review against a coherent ledger snapshot.

This does not record a correction or reuse a persisted reconciliation result.
Both the current and proposed statement identities are computed from current
admitted rows. Native file control totals are a different check and are never
claimed to have been verified by this preview.
"""
import uuid
from dataclasses import replace

from sqlalchemy import select

from postgres.models.financial import FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction
from services.financial.duplicate_decisions import duplicate_revision
from services.financial.money import Money
from services.financial.periods import read_opening, read_closing
from services.financial.reconcile import total_transactions, evaluate_identity
from services.financial.transaction_query import to_view
from services.financial.correction_verification import correction_verification
from services.financial.documents import UnknownSourceShapeError
from postgres.models.enums import ReconciliationStatus


class CorrectionPreviewError(ValueError):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


def preview_amount_correction(session, *, case_id: uuid.UUID, transaction_id: uuid.UUID,
                              amount_minor: int, direction: str) -> dict:
    """Preview one magnitude/direction change without changing rows or classes.

    Document-first locks match the disposition writers and are held until the
    caller closes its transaction. The revision must be rechecked by a future
    correction writer; a successful preview is never permission to write stale
    data. Existing quarantine is preserved, not silently released by an edit.
    """
    if type(amount_minor) is not int or not 0 <= amount_minor <= 9223372036854775807:
        raise CorrectionPreviewError("Amount must be a nonnegative integer within the ledger's range.")
    if direction not in {"credit", "debit"}:
        raise CorrectionPreviewError("Direction must be credit or debit.")
    document_id = session.scalar(select(FinancialTransaction.source_document_id).where(
        FinancialTransaction.id == transaction_id, FinancialTransaction.case_id == case_id))
    document = session.scalar(select(FinancialSourceDocument).where(
        FinancialSourceDocument.id == document_id, FinancialSourceDocument.case_id == case_id
    ).with_for_update().execution_options(populate_existing=True))
    if document is None:
        raise CorrectionPreviewError("Ledger row not found in this case.", 404)
    periods = list(session.scalars(select(FinancialStatementPeriod).where(
        FinancialStatementPeriod.source_document_id == document.id
    ).order_by(FinancialStatementPeriod.id).with_for_update().execution_options(populate_existing=True)))
    rows = list(session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.source_document_id == document.id
    ).order_by(FinancialTransaction.id).with_for_update().execution_options(populate_existing=True)))
    row = next((row for row in rows if row.id == transaction_id and row.case_id == case_id), None)
    if row is None:
        raise CorrectionPreviewError("Ledger row not found in this case.", 404)
    if document.status != "admitted" or row.ledger_status not in {"admitted", "quarantined"} or row.superseded_by_id:
        raise CorrectionPreviewError("Only a current row in an admitted document can be reviewed for correction.", 409)
    if any(p.case_id != case_id for p in periods) or any(r.case_id != case_id for r in rows):
        raise CorrectionPreviewError("The source document has inconsistent case ownership.", 409)
    period_ids = {period.id for period in periods}
    if any(r.statement_period_id is not None and r.statement_period_id not in period_ids for r in rows):
        raise CorrectionPreviewError("A source row links to another document's statement period.", 409)
    if amount_minor == row.amount_minor and direction == row.direction:
        raise CorrectionPreviewError("The proposed reading is unchanged.")
    original = to_view(row).to_json()
    # Decimal strings preserve all PostgreSQL BIGINT values in JavaScript.
    original["amount_minor"] = str(row.amount_minor)
    original["running_balance_minor"] = None if row.running_balance_minor is None else str(row.running_balance_minor)
    result = {
        "case_id": str(case_id), "transaction_id": str(row.id),
        "document_revision": duplicate_revision(session, document),
        "original": original,
        "proposed": {"amount_minor": str(amount_minor), "direction": direction,
                     "currency": row.currency, "ledger_status": row.ledger_status},
        "statement_identity": None,
        "limitation": "No linked statement period; statement balance impact is unavailable.",
        "applied": False,
        "native_controls_rechecked": False,
        "proof_class_changed": False,
    }
    statuses = []
    for period in periods:
        period_rows = list(session.scalars(select(FinancialTransaction).where(
            FinancialTransaction.statement_period_id == period.id)))
        if any(r.case_id != case_id or r.source_document_id != document.id or r.account_id != period.account_id
               for r in period_rows):
            raise CorrectionPreviewError("The statement period has inconsistent row ownership.", 409)
        affected = period.id == row.statement_period_id
        if affected and period.currency != row.currency:
            raise CorrectionPreviewError("The row and period currencies disagree.", 409)
        totals = total_transactions(session, period_id=period.id, currency=period.currency)
        credits, debits = totals.credits.minor_units, totals.debits.minor_units
        if affected and row.ledger_status == "admitted":
            credits -= row.amount_minor if row.direction == "credit" else 0
            debits -= row.amount_minor if row.direction == "debit" else 0
            credits += amount_minor if direction == "credit" else 0
            debits += amount_minor if direction == "debit" else 0
        proposed = replace(totals, credits=Money(credits, period.currency), debits=Money(debits, period.currency))
        def identity(value):
            outcome = evaluate_identity(opening=read_opening(period), closing=read_closing(period),
                                        totals=value, currency=period.currency)
            return {"status": outcome.status.value,
                    "credits_minor": str(value.credits.minor_units), "debits_minor": str(value.debits.minor_units),
                    "delta_minor": None if outcome.delta is None else str(outcome.delta.minor_units),
                    "counted": value.counted, "excluded": dict(value.excluded),
                    "independent_balances": outcome.independent}
        projected = identity(proposed)
        statuses.append(ReconciliationStatus(projected["status"]))
        if affected:
            result["statement_identity"] = {"period_id": str(period.id), "current": identity(totals), "proposed": projected}
            result["limitation"] = "Statement balance only; native controls and running-balance chains are not revalidated. Existing quarantine is preserved."
    try:
        result["verification"] = correction_verification(document, rows, statuses)
    except (UnknownSourceShapeError, ValueError):
        result["verification"] = {"can_record": False, "current_proof_class": document.proof_class,
                                  "proposed_proof_class": None, "reservations": [],
                                  "included_in_default_totals": False,
                                  "scope": "all rows in this source document",
                                  "reason": "Source classification or reservations are unavailable or inconsistent; recording is refused."}
    return result
