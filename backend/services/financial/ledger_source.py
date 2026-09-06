"""Resolve a relational ledger citation to its same-case evidence file.

Stored locators are retained, not inferred from an amount or row number. Hash
comparison checks recorded provenance; it does not reread evidence bytes.
"""
import re
from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from services.financial.locators import Locator, LocatorError
from services.financial.transactions import LOCATOR_PROVENANCE_KEY


class LedgerSourceError(ValueError):
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


def ledger_source(session, *, case_id, transaction_id):
    source = session.execute(select(FinancialTransaction, FinancialSourceDocument, EvidenceFile)
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
            "source_document_id": str(document.id), "evidence_file_id": str(evidence.id),
            "filename": evidence.original_filename, "sha256_at_ingestion": document.sha256_at_ingestion,
            "recorded_digest_matches": True, "file_bytes_verified": False,
            "ledger_status": row.ledger_status,
            "superseded_by_id": str(row.superseded_by_id) if row.superseded_by_id else None,
            "locator": locator, "locator_state": state,
            "limitation": "Stored source citation only; this does not verify the reading or admit it to totals."}
