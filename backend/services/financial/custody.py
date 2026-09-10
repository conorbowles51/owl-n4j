"""Reported source custody is not a finding of authenticity or a fresh byte check."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile
from postgres.models.financial_custody import FinancialCustodyEvent
from services.financial.candidate_store import CandidateStoreError

LIMITATION = ('These are attributed custody reports, not independently verified custody or authenticity. '
              'Reported event times are distinct from recording times. Missing history is unknown. '
              'Stored source and certification hashes are not fresh byte checks.')


class CustodyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    event_id: UUID
    expected_source_sha256: str | None = Field(pattern=r'^[a-f0-9]{64}$')
    event_kind: Literal['receipt', 'transfer', 'note', 'correction']
    occurred_at: AwareDatetime | None = None
    from_person_or_organisation: str | None = Field(default=None, min_length=1, max_length=512)
    received_by: str | None = Field(default=None, min_length=1, max_length=512)
    acquisition_method: Literal['production', 'subpoena', 'client', 'open_source', 'other', 'unknown'] = 'unknown'
    native_file_status: Literal['provided', 'requested', 'unavailable', 'unknown'] = 'unknown'
    certification_file_id: UUID | None = None
    corrects_event_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=4096)

    @model_validator(mode='after')
    def validate_report(self):
        if (self.event_kind == 'correction') != (self.corrects_event_id is not None):
            raise ValueError('A correction must identify its earlier custody event; other events cannot correct one.')
        if self.event_kind in ('receipt', 'transfer') and not self.received_by:
            raise ValueError('Identify the receiving person or organisation for a receipt or transfer.')
        return self


def custody_view(row):
    return dict(id=str(row.id), case_id=str(row.case_id), evidence_file_id=str(row.evidence_file_id),
                evidence_sha256=row.evidence_sha256, recorded_at=row.recorded_at.isoformat(),
                actor=row.actor, report=row.report)


def source_custody(session, *, case_id, file_id):
    source = session.scalar(select(EvidenceFile).where(EvidenceFile.id == file_id, EvidenceFile.case_id == case_id))
    if source is None:
        raise CandidateStoreError('Source not found in this case.', 404)
    rows = list(session.scalars(select(FinancialCustodyEvent).where(
        FinancialCustodyEvent.case_id == case_id, FinancialCustodyEvent.evidence_file_id == file_id)
        .order_by(FinancialCustodyEvent.recorded_at, FinancialCustodyEvent.id).limit(1001)))
    if len(rows) > 1000:
        raise CandidateStoreError('Custody history exceeds the supported capture limit.', 422)
    return dict(case_id=str(case_id), evidence_file_id=str(file_id), evidence_sha256=source.sha256, events=[custody_view(r) for r in rows], limitation=LIMITATION)


def record_custody(session, *, case_id, file_id, request, actor):
    request = CustodyRequest.model_validate(request)
    source = session.scalar(select(EvidenceFile).where(EvidenceFile.id == file_id,
        EvidenceFile.case_id == case_id).with_for_update())
    if source is None:
        raise CandidateStoreError('Source not found in this case.', 404)
    report = request.model_dump(mode='json', exclude={'event_id', 'expected_source_sha256'})
    existing = session.get(FinancialCustodyEvent, request.event_id)
    if existing is not None:
        original = {k: v for k, v in existing.report.items() if k != 'certification_sha256'}
        if (existing.case_id != case_id or existing.evidence_file_id != file_id or original != report
                or existing.actor != actor or existing.evidence_sha256 != request.expected_source_sha256):
            raise CandidateStoreError('This custody event identifier was already used for different content.', 409)
        return custody_view(existing)
    if source.sha256 != request.expected_source_sha256:
        raise CandidateStoreError('The registered source hash changed. Reload before recording custody.', 409)
    if request.corrects_event_id:
        previous = session.get(FinancialCustodyEvent, request.corrects_event_id)
        if previous is None or previous.case_id != case_id or previous.evidence_file_id != file_id:
            raise CandidateStoreError('The corrected event must belong to this source and case.', 422)
    report['certification_sha256'] = None
    if request.certification_file_id:
        certificate = session.scalar(select(EvidenceFile).where(EvidenceFile.id == request.certification_file_id,
            EvidenceFile.case_id == case_id).with_for_update())
        if certificate is None or certificate.id == source.id:
            raise CandidateStoreError('Choose a separate certification file in this case.', 422)
        report['certification_sha256'] = certificate.sha256
    event = FinancialCustodyEvent(id=request.event_id, case_id=case_id, evidence_file_id=file_id,
        evidence_sha256=source.sha256, actor=actor, report=report)
    session.add(event)
    session.flush()
    return custody_view(event)


def capture_case_custody(session, *, case_id):
    """Include reports for removed sources as well; never reconstruct missing events."""
    rows = list(session.scalars(select(FinancialCustodyEvent).where(FinancialCustodyEvent.case_id == case_id)
        .order_by(FinancialCustodyEvent.recorded_at, FinancialCustodyEvent.id).limit(10001)))
    if len(rows) > 10000:
        from services.financial.ledger_summary import LedgerSummaryError
        raise LedgerSummaryError('Case custody reports exceed the export limit; no partial history was produced.')
    return dict(case_id=str(case_id), events=[custody_view(row) for row in rows], limitation=LIMITATION,
        scope='All recorded custody reports in this case, including reports for subsequently removed source registrations. Not limited by ledger filters.')
