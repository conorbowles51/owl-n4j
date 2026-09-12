"""Resolve a relational ledger citation to its same-case evidence file.

Stored locators are retained, not inferred from an amount or row number. Hash
comparison checks recorded provenance; it does not reread evidence bytes.
"""
import re
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from services.financial.locators import Locator, LocatorError
from services.financial.transactions import LOCATOR_PROVENANCE_KEY
from services.financial.transaction_query import to_view


class LedgerSourceError(ValueError):
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


def ledger_source(session, *, case_id, transaction_id):
    source = session.execute(select(FinancialTransaction, FinancialSourceDocument, EvidenceFile).options(joinedload(FinancialTransaction.account))
        .join(FinancialSourceDocument, FinancialTransaction.source_document_id == FinancialSourceDocument.id)
        .join(EvidenceFile, FinancialSourceDocument.evidence_file_id == EvidenceFile.id)
        .where(FinancialTransaction.id == transaction_id, FinancialTransaction.case_id == case_id,
               FinancialSourceDocument.case_id == case_id, EvidenceFile.case_id == case_id)).one_or_none()
    if source is None:
        raise LedgerSourceError("Ledger source not found in this case.", 404)
    row, document, evidence = source
    if (not isinstance(document.sha256_at_ingestion, str)
            or re.fullmatch(r"[a-f0-9]{64}", document.sha256_at_ingestion) is None
            or evidence.sha256 != document.sha256_at_ingestion):
        raise LedgerSourceError("The evidence file's recorded digest differs from the ledger source. Source navigation is unavailable.")
    raw = row.provenance.get(LOCATOR_PROVENANCE_KEY) if isinstance(row.provenance, dict) else None
    locator = None
    state = "missing" if raw is None else "invalid"
    if raw is not None:
        try:
            if isinstance(raw, dict) and "page" in raw and (type(raw["page"]) is not int or raw["page"] < 1):
                raise ValueError("Invalid page")
            parsed = Locator.from_json(raw)
            if parsed.page is not None and document.page_count is not None and parsed.page > document.page_count:
                raise ValueError("Page exceeds source")
            locator = parsed.to_json()
            state = "stored"
        except (LocatorError, ValueError, TypeError, KeyError):
            pass
    return {"case_id": str(case_id), "transaction_id": str(row.id), "ref_id": row.ref_id,
            "transaction": to_view(row, account=row.account).to_json(),
            "source_document_id": str(document.id), "evidence_file_id": str(evidence.id),
            "filename": evidence.original_filename, "sha256_at_ingestion": document.sha256_at_ingestion,
            "recorded_digest_matches": True, "file_bytes_verified": False,
            "ledger_status": row.ledger_status,
            "superseded_by_id": str(row.superseded_by_id) if row.superseded_by_id else None,
            "locator": locator, "locator_state": state,
            "limitation": "Stored source citation only; this does not verify the reading or admit it to totals."}


def statement_source(session, *, case_id, period_id):
    """Open a period's registered file without inventing a page or highlight."""
    from postgres.models.financial import FinancialStatementPeriod, FinancialAccount
    result = session.execute(select(FinancialStatementPeriod, FinancialSourceDocument, EvidenceFile)
        .join(FinancialSourceDocument, FinancialStatementPeriod.source_document_id == FinancialSourceDocument.id)
        .join(FinancialAccount, FinancialStatementPeriod.account_id == FinancialAccount.id)
        .join(EvidenceFile, FinancialSourceDocument.evidence_file_id == EvidenceFile.id)
        .where(FinancialStatementPeriod.id == period_id, FinancialStatementPeriod.case_id == case_id,
            FinancialAccount.case_id == case_id, FinancialSourceDocument.case_id == case_id,
            EvidenceFile.case_id == case_id)).one_or_none()
    if result is None:
        raise LedgerSourceError('Statement source file not found in this case.', 404)
    period, document, evidence = result
    if (not isinstance(document.sha256_at_ingestion, str)
            or re.fullmatch(r'[a-f0-9]{64}', document.sha256_at_ingestion) is None
            or evidence.sha256 != document.sha256_at_ingestion):
        raise LedgerSourceError('The evidence file recorded digest differs from the statement source.')
    return dict(case_id=str(case_id), period_id=str(period.id), source_document_id=str(document.id),
        evidence_file_id=str(evidence.id), filename=evidence.original_filename,
        recorded_digest_matches=True, file_bytes_verified=False,
        reviewed_controls=_statement_controls(session, period, document, evidence),
        limitation='Registered source file and any retained finalization control readings. These citations do not revalidate current financial readings.')


def _statement_controls(session, period, document, evidence):
    """Return sealed control citations, never infer controls for legacy periods."""
    if document.document_type == 'statement_review':
        from services.financial.statement_import_controls import read_import_controls
        try:
            return read_import_controls(period, document, evidence)
        except (ValueError, TypeError, KeyError, AttributeError, LocatorError) as exc:
            raise LedgerSourceError('The saved statement balances or their PDF locations could not be checked.') from exc
    from postgres.models.financial_candidates import FinancialCandidateFinalization
    from services.financial.pdf_candidates import _digest
    from services.financial.candidate_statement_scopes import ReviewedStatementScope
    receipts = session.scalars(select(FinancialCandidateFinalization).where(
        FinancialCandidateFinalization.case_id == period.case_id,
        FinancialCandidateFinalization.source_document_id == document.id,
        FinancialCandidateFinalization.evidence_file_id == evidence.id)).all()
    found = []
    try:
        for receipt in receipts:
            snapshot = receipt.snapshot
            if _digest(snapshot) != receipt.snapshot_sha256:
                raise ValueError('Inconsistent finalization receipt')
            records = snapshot.get('statement_periods', [])
            for record in records:
                if record['period_id'] != str(period.id):
                    continue
                if record['account_id'] != str(period.account_id) or record['currency'] != period.currency:
                    raise ValueError('Mismatched statement link')
                matches = [scope for scope in snapshot['manifest']['statement_scopes']
                    if scope['account_id'] == record['account_id'] and scope['currency'] == record['currency']
                    and scope['candidate_ids'] == record['candidate_ids']]
                if len(matches) != 1:
                    raise ValueError('Ambiguous statement controls')
                raw = matches[0]
                reviewed = ReviewedStatementScope.model_validate({key: value for key, value in raw.items() if key != 'bound_controls'})
                controls = []
                for role in ('start', 'end', 'opening', 'closing', 'credits_total', 'debits_total'):
                    reading = getattr(reviewed, role)
                    bound = raw['bound_controls'].get(role) if role.endswith('_total') else raw['bound_controls'][role]
                    if reading is None:
                        if bound is not None:
                            raise ValueError('Unexpected absent control')
                        continue
                    if {key: value for key, value in bound.items() if key != 'locator'} != reading.model_dump(mode='json'):
                        raise ValueError('Inconsistent bound control')
                    locator = Locator.from_json(bound['locator'])
                    if locator.page != reading.source.page_number or (document.page_count is not None and locator.page > document.page_count):
                        raise ValueError('Invalid control page')
                    controls.append(dict(role=role, original_text=reading.source.expected_text,
                        reviewed_value=reading.value if role in ('start', 'end') else reading.amount_minor,
                        locator=locator.to_json()))
                found.append(dict(finalization_id=str(receipt.id), currency=reviewed.currency,
                    balance_convention=reviewed.balance_convention, reason=reviewed.reason,
                    controls=controls, scope='Readings and source cells retained at finalization; current values may differ after later changes.'))
        if len(found) > 1:
            raise ValueError('Repeated statement controls')
    except (ValueError, TypeError, KeyError, AttributeError, LocatorError) as exc:
        raise LedgerSourceError('Retained statement control citations are inconsistent.') from exc
    return found[0] if found else None
