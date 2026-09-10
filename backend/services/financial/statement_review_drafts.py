"""Case-scoped saved controls. Drafts do not admit rows or certify statements."""
from copy import deepcopy
from datetime import datetime, timezone
from typing import Annotated
from pydantic import Field
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialAccount
from postgres.models.financial_candidates import FinancialStatementReviewDraft, FinancialCandidateFinalization, FinancialCandidateMapping, FinancialExtractionCandidate
from services.financial.candidate_statement_scopes import StatementScopesRequest
from services.financial.candidate_store import CandidateStoreError
from services.financial.pdf_candidates import _digest
from services.financial.decisions import Actor

class StatementDraftRequest(StatementScopesRequest):
    expected_revision: Annotated[str | None, Field(pattern=r'^[a-f0-9]{64}$')] = None


def _view(row, case_id, file_id):
    scopes = deepcopy(row.statement_scopes) if row else []
    return dict(case_id=str(case_id), evidence_file_id=str(file_id), statement_scopes=scopes,
        revision=_digest(dict(case_id=str(case_id), file_id=str(file_id), version=row.version, scopes=scopes)) if row else None,
        saved_at=row.updated_at.isoformat() if row else None, actor=deepcopy(row.actor) if row else None,
        applied=False)


def read_statement_draft(session, *, case_id, evidence_file_id):
    if session.scalar(select(EvidenceFile.id).where(EvidenceFile.id==evidence_file_id, EvidenceFile.case_id==case_id)) is None:
        raise CandidateStoreError('Source file not found in this case.', 404)
    row = session.get(FinancialStatementReviewDraft, evidence_file_id, populate_existing=True)
    if row and row.case_id != case_id:
        raise CandidateStoreError('Draft ownership is inconsistent.', 409)
    return _view(row, case_id, evidence_file_id)


def save_statement_draft(session, *, case_id, evidence_file_id, request, actor):
    if not isinstance(actor, Actor) or session.new or session.dirty or session.deleted:
        raise CandidateStoreError('Use an identified actor and a clean session.', 422)
    request = StatementDraftRequest.model_validate(request)
    try:
        if session.scalar(select(EvidenceFile.id).where(EvidenceFile.id==evidence_file_id, EvidenceFile.case_id==case_id).with_for_update()) is None:
            raise CandidateStoreError('Source file not found in this case.', 404)
        if session.scalar(select(FinancialCandidateFinalization.id).where(FinancialCandidateFinalization.case_id==case_id,
                FinancialCandidateFinalization.evidence_file_id==evidence_file_id)) is not None:
            raise CandidateStoreError('This PDF is finalized; its recorded statement controls cannot be edited through a draft.', 409)
        row = session.get(FinancialStatementReviewDraft, evidence_file_id, populate_existing=True)
        if row and row.case_id != case_id:
            raise CandidateStoreError('Draft ownership is inconsistent.', 409)
        current = _view(row, case_id, evidence_file_id)
        if request.expected_revision != current['revision']:
            raise CandidateStoreError('Saved statement controls changed. Load the current draft before saving.', 409)
        ids = [cid for scope in request.statement_scopes for cid in scope.candidate_ids]
        if len(ids) > 1000:
            raise CandidateStoreError("A statement draft is limited to 1,000 selected readings.", 422)
        if len(ids) != len(set(ids)):
            raise CandidateStoreError('A reading cannot be assigned to multiple draft statements.', 422)
        if ids:
            owned = set(session.scalars(select(FinancialExtractionCandidate.id).join(FinancialCandidateMapping,
                FinancialCandidateMapping.id==FinancialExtractionCandidate.mapping_id).where(
                FinancialExtractionCandidate.id.in_(ids), FinancialCandidateMapping.case_id==case_id,
                FinancialCandidateMapping.evidence_file_id==evidence_file_id)))
            if owned != set(ids): raise CandidateStoreError('Draft rows must belong to this PDF and case.', 422)
        account_ids = {scope.account_id for scope in request.statement_scopes}
        if account_ids and set(session.scalars(select(FinancialAccount.id).where(FinancialAccount.id.in_(account_ids),
                FinancialAccount.case_id==case_id))) != account_ids:
            raise CandidateStoreError('Draft accounts must belong to this case.', 422)
        scopes = [scope.model_dump(mode='json') for scope in request.statement_scopes]
        if row is None:
            row = FinancialStatementReviewDraft(evidence_file_id=evidence_file_id, case_id=case_id, version=1)
            session.add(row)
        else:
            row.version += 1
        row.statement_scopes = scopes
        row.actor = dict(name=actor.name, email=actor.email, user_id=str(actor.user_id) if actor.user_id else None)
        row.updated_at = datetime.now(timezone.utc)
        session.flush()
        result = _view(row, case_id, evidence_file_id)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
