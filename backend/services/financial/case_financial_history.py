"""Optional case-wide financial review history, separate from ledger totals."""
from sqlalchemy import select
from services.financial.audit_chain import capture_financial_audit_chain
from postgres.models.financial import AdjudicationEvent
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialCandidateFinalization
from services.financial.decision_log import to_record, _machine_actor_email
from services.financial.ledger_review_history import capture_pdf_review_history
from services.financial.ledger_summary import LedgerSummaryError

MAX_CASE_HISTORY_RECORDS = 10000


def capture_case_financial_history(session, *, case_id):
    events = list(session.scalars(select(AdjudicationEvent).where(AdjudicationEvent.case_id == case_id)
        .order_by(AdjudicationEvent.subject_type, AdjudicationEvent.subject_id, AdjudicationEvent.subject_sequence)
        .limit(MAX_CASE_HISTORY_RECORDS + 1)))
    if len(events) > MAX_CASE_HISTORY_RECORDS:
        raise LedgerSummaryError('Case financial decision history exceeds the export limit; no partial history was produced.')
    sequences = {}
    for event in events:
        key = (event.subject_type, event.subject_id)
        expected = sequences.get(key, 0) + 1
        if event.subject_sequence != expected:
            raise LedgerSummaryError('Recorded case decision history has a sequence gap; export refused.')
        sequences[key] = expected
    files = set()
    for model in (FinancialCandidateMapping, FinancialCandidateFinalization):
        files.update(session.scalars(select(model.evidence_file_id).where(model.case_id == case_id)
            .distinct().limit(MAX_CASE_HISTORY_RECORDS + 1)))
        if len(files) > MAX_CASE_HISTORY_RECORDS:
            raise LedgerSummaryError('Case PDF review scope exceeds the export limit; no partial history was produced.')
    reviews = capture_pdf_review_history(session, case_id=case_id, evidence_file_ids=files)
    reviews['scope'] = 'All recorded PDF candidate mappings and finalizations in this case, including pending and rejected readings outside the exported ledger scope.'
    machine_email = _machine_actor_email()
    return dict(schema_version='loupe.financial.case_review_history/1', case_id=str(case_id),
        scope='All recorded financial adjudication events and saved PDF candidate review history, plus available case audit events at capture time. Account/date/table filters do not limit this appendix.',
        decisions=[to_record(event, machine_email=machine_email).as_dict() for event in events],
        decision_order='Per-subject sequence only; ordering across subjects does not establish chronology.',
        pdf_review_history=reviews,
        audit_chain=capture_financial_audit_chain(session, case_id=case_id),
        limitation='Separate review context, never additional ledger totals. This does not contain all Workspace, entity-merge, custody, or other application history, and does not establish a complete case audit spine.')
