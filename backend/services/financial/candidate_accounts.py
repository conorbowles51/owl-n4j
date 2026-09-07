"""Explicit, document-scoped provisional accounts for candidate review.

A reviewer label is not a printed account identifier. Never use it to join across
files or currencies. Creation is attributed to an ingestion run; no ledger money
or candidate review is changed. Known-account discovery remains a separate path.
"""
from types import SimpleNamespace
from typing import Annotated
from pydantic import Field, model_validator
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialAccount
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialExtractionCandidate
from services.financial.accounts import AccountDraft, record_account
from services.financial.candidate_assessment import current_candidate_original
from services.financial.candidate_reviews import read_candidate_review
from services.financial.candidate_store import CandidateStoreError
from services.financial.decisions import Actor
from services.financial.money import MoneyError, get_currency
from services.financial.pdf_candidates import _Contract, _Digest, _digest
from services.financial.runs import ingestion_run


class CandidateAccountRequest(_Contract):
    expected_revision: _Digest
    label: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    currency: Annotated[str, Field(strict=True, pattern=r'^[A-Z]{3}$')]
    reason: Annotated[str, Field(strict=True, min_length=1, max_length=4096)]

    @model_validator(mode='after')
    def explicit_account_context(self):
        if not self.label.strip() or not self.reason.strip():
            raise ValueError('An account label and reason are required.')
        try:
            get_currency(self.currency)
        except MoneyError as exc:
            raise ValueError(str(exc)) from exc
        return self


def create_candidate_account(*, session_factory, case_id, candidate_id, request, actor):
    if not isinstance(actor, Actor):
        raise CandidateStoreError('An identified actor is required.', 422)
    request = CandidateAccountRequest.model_validate(request)
    with session_factory() as session:
        file_id = session.scalar(select(FinancialCandidateMapping.evidence_file_id)
            .join(FinancialExtractionCandidate, FinancialExtractionCandidate.mapping_id == FinancialCandidateMapping.id)
            .where(FinancialCandidateMapping.case_id == case_id, FinancialExtractionCandidate.id == candidate_id))
        if file_id is None:
            raise CandidateStoreError('Candidate not found in this case.', 404)
    label = request.label.strip()
    draft = AccountDraft.unidentified(distinguisher='candidate-account:' + _digest(dict(
        evidence_file_id=str(file_id), currency=request.currency, label=label)), currency=request.currency,
        metadata=dict(display_label=label, candidate_account_source_file_id=str(file_id),
                      label_origin='investigator_provisional_label'))
    with ingestion_run(case_id=case_id, actor=SimpleNamespace(id=actor.user_id, email=actor.email),
            session_factory=session_factory, config=dict(operation='provisional_candidate_account',
                candidate_id=str(candidate_id), evidence_file_id=str(file_id),
                request=request.model_dump(mode='json'), actor_name=actor.name),
            notes='Explicit provisional account setup; no transaction admission.') as run:
        with session_factory() as session:
            try:
                if session.scalar(select(EvidenceFile.id).where(EvidenceFile.id == file_id,
                        EvidenceFile.case_id == case_id).with_for_update()) is None:
                    raise CandidateStoreError('Candidate source not found in this case.', 404)
                if session.scalar(select(EvidenceDocumentText.evidence_file_id).where(
                        EvidenceDocumentText.evidence_file_id == file_id).with_for_update()) is None:
                    raise CandidateStoreError('Candidate source text is missing.', 404)
                # Lock all stored geometry for this file before rebinding the nominated page.
                session.execute(select(EvidenceTableGeometry.page_number).where(
                    EvidenceTableGeometry.evidence_file_id == file_id)
                    .order_by(EvidenceTableGeometry.page_number).with_for_update()).all()
                current_candidate_original(session, case_id=case_id, candidate_id=candidate_id)
                state = read_candidate_review(session, case_id=case_id, candidate_id=candidate_id)
                if state['review_revision'] != request.expected_revision:
                    raise CandidateStoreError('Candidate review changed. Reload before creating an account.')
                existing = session.scalar(select(FinancialAccount).where(FinancialAccount.case_id == case_id,
                    FinancialAccount.identity_key == draft.identity().key).with_for_update())
                if existing is not None and (existing.currency != request.currency or
                        (existing.metadata_ or {}).get('candidate_account_source_file_id') != str(file_id)):
                    raise CandidateStoreError('Existing provisional account context is inconsistent.')
                account = record_account(session, run, draft)
                result = dict(case_id=str(case_id), candidate_id=str(candidate_id), evidence_file_id=str(file_id),
                    review_revision=state['review_revision'], created=existing is None, applied=False,
                    account=dict(id=str(account.id), identifier=account.identifier_as_printed,
                        holder=account.holder_name, institution=account.institution_name, currency=account.currency,
                        display_label=label, provisional=True, source_file_id=str(file_id)), run_id=str(run.run_id))
                session.commit()
            except Exception:
                session.rollback()
                raise
    return result
