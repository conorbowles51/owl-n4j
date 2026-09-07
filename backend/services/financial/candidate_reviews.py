"""Append reviewed readings; resolution is not ledger admission or proof class."""
from copy import deepcopy
from datetime import date
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import Field, model_validator
from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceTableGeometry
from postgres.models.financial import FinancialAccount
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialCandidateReview, FinancialExtractionCandidate
from services.financial.candidate_store import CandidateStoreError
from services.financial.decisions import Actor
from services.financial.money import MoneyError, get_currency
from services.financial.pdf_candidates import _Contract, _Digest, _digest


class CandidateResolvedReading(_Contract):
    account_id: UUID
    currency: Annotated[str, Field(strict=True, pattern=r"^[A-Z]{3}$")]
    amount_minor: Annotated[str, Field(strict=True, pattern=r"^(0|[1-9][0-9]{0,18})$")]
    direction: Literal["credit", "debit"]
    booking_date: Optional[str] = None
    value_date: Optional[str] = None
    transaction_date: Optional[str] = None
    description: Annotated[str, Field(strict=True, max_length=4096)]

    @model_validator(mode="after")
    def complete_exact_reading(self):
        if int(self.amount_minor) > 9223372036854775807:
            raise ValueError("Amount exceeds the ledger's exact integer range.")
        try:
            get_currency(self.currency)
        except MoneyError as exc:
            raise ValueError(str(exc)) from exc
        dates = [self.booking_date, self.value_date, self.transaction_date]
        if not any(dates):
            raise ValueError("At least one explicitly identified date is required.")
        for value in dates:
            if value is not None:
                parsed = date.fromisoformat(value)
                if parsed.isoformat() != value:
                    raise ValueError("Dates must use YYYY-MM-DD without an inferred year or time.")
        return self


class CandidateReviewRequest(_Contract):
    expected_revision: _Digest
    status: Literal["pending", "resolved", "rejected"]
    reason: Annotated[str, Field(strict=True, min_length=1, max_length=4096)]
    reading: Optional[CandidateResolvedReading] = None

    @model_validator(mode="after")
    def coherent_decision(self):
        if not self.reason.strip():
            raise ValueError("A review reason is required.")
        if (self.status == "resolved") != (self.reading is not None):
            raise ValueError("Only a resolved review must carry a complete reading.")
        return self


def candidate_review_state(session, *, candidate, events=None):
    if events is None:
        events = list(session.scalars(select(FinancialCandidateReview).where(
            FinancialCandidateReview.candidate_id == candidate.id).order_by(FinancialCandidateReview.sequence)))
    revision = _digest(dict(candidate_id=str(candidate.id), original_sha256=candidate.snapshot_sha256, sequence=0))
    history = []
    for sequence, event in enumerate(events, 1):
        if (event.sequence != sequence or event.original_sha256 != candidate.snapshot_sha256
                or event.previous_revision != revision):
            raise CandidateStoreError("Candidate review history is incomplete or inconsistent.")
        entry = dict(id=str(event.id), sequence=event.sequence, status=event.status,
            reason=event.reason, reading=deepcopy(event.reading), actor=deepcopy(event.actor),
            created_at=event.created_at.isoformat())
        revision = _digest(dict(previous_revision=revision, event=entry))
        history.append(entry)
    latest = history[-1] if history else None
    return dict(status=latest["status"] if latest else "pending",
        reading=deepcopy(latest["reading"]) if latest else None,
        review_revision=revision, history=history)


def read_candidate_review(session, *, case_id, candidate_id):
    candidate = session.scalar(select(FinancialExtractionCandidate)
        .join(FinancialCandidateMapping, FinancialCandidateMapping.id == FinancialExtractionCandidate.mapping_id)
        .where(FinancialExtractionCandidate.id == candidate_id, FinancialCandidateMapping.case_id == case_id))
    if candidate is None:
        raise CandidateStoreError("Candidate not found in this case.", 404)
    if _digest(candidate.snapshot) != candidate.snapshot_sha256:
        raise CandidateStoreError("Candidate original is inconsistent.")
    return dict(candidate_id=str(candidate.id), case_id=str(case_id), original=deepcopy(candidate.snapshot),
                **candidate_review_state(session, candidate=candidate), applied=False)


def review_candidate(session, *, case_id, candidate_id, request, actor):
    """Owns commit/rollback; requires a clean dedicated session and authorized actor."""
    from services.financial.candidate_assessment import current_candidate_original
    if not isinstance(actor, Actor) or session.new or session.dirty or session.deleted:
        raise CandidateStoreError("Use an identified actor and a clean dedicated session.", 422)
    request = CandidateReviewRequest.model_validate(request)
    try:
        mapping = session.scalar(select(FinancialCandidateMapping)
            .join(FinancialExtractionCandidate, FinancialExtractionCandidate.mapping_id == FinancialCandidateMapping.id)
            .where(FinancialExtractionCandidate.id == candidate_id, FinancialCandidateMapping.case_id == case_id))
        if mapping is None:
            raise CandidateStoreError("Candidate not found in this case.", 404)
        file_id = session.scalar(select(EvidenceFile.id).where(EvidenceFile.id == mapping.evidence_file_id,
            EvidenceFile.case_id == case_id).with_for_update())
        if file_id is None:
            raise CandidateStoreError("Candidate source not found in this case.", 404)
        if session.scalar(select(EvidenceDocumentText.evidence_file_id).where(
                EvidenceDocumentText.evidence_file_id == file_id).with_for_update()) is None:
            raise CandidateStoreError("Candidate source text is missing.", 404)
        proposal = mapping.snapshot["proposal"]
        if proposal["schema_version"] == "pdf-grid-mapping-v1":
            if session.scalar(select(EvidenceTableGeometry.page_number).where(
                    EvidenceTableGeometry.evidence_file_id == file_id,
                    EvidenceTableGeometry.page_number == proposal["page_number"]).with_for_update()) is None:
                raise CandidateStoreError("Candidate source geometry is missing.", 404)
        candidate = session.scalar(select(FinancialExtractionCandidate).where(
            FinancialExtractionCandidate.id == candidate_id).with_for_update().execution_options(populate_existing=True))
        if candidate is None:
            raise CandidateStoreError("Candidate not found in this case.", 404)
        current_candidate_original(session, case_id=case_id, candidate_id=candidate_id)
        state = candidate_review_state(session, candidate=candidate)
        if request.expected_revision != state["review_revision"]:
            raise CandidateStoreError("Candidate review changed. Reload before deciding.")
        reading = request.reading.model_dump(mode="json") if request.reading is not None else None
        if state["status"] == request.status and state["reading"] == reading:
            raise CandidateStoreError("This candidate already has that review state.")
        if request.reading is not None:
            account = session.scalar(select(FinancialAccount).where(FinancialAccount.id == request.reading.account_id,
                FinancialAccount.case_id == case_id).with_for_update().execution_options(populate_existing=True))
            if account is None or (account.currency is not None and account.currency != request.reading.currency):
                raise CandidateStoreError("Reviewed account is missing from this case or uses a different currency.", 422)
            provisional_source = (account.metadata_ or {}).get("candidate_account_source_file_id")
            if provisional_source is not None and provisional_source != str(file_id):
                raise CandidateStoreError("This provisional account belongs to a different source PDF.", 422)
        event = FinancialCandidateReview(candidate_id=candidate.id, sequence=len(state["history"])+1,
            status=request.status, reason=request.reason, reading=reading,
            original_sha256=candidate.snapshot_sha256, previous_revision=state["review_revision"],
            actor=dict(name=actor.name, email=actor.email, user_id=str(actor.user_id) if actor.user_id else None))
        session.add(event)
        session.flush()
        result = read_candidate_review(session, case_id=case_id, candidate_id=candidate.id)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
