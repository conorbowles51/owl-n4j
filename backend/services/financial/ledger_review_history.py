"""Capture PDF review originals and decisions for the ledger's source files."""
from collections import Counter
from datetime import date, datetime
from uuid import UUID
from sqlalchemy import select
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.pdf_candidates import _digest
from services.financial.candidate_reviews import candidate_review_state
from services.financial.candidate_store import CandidateStoreError
from postgres.models.financial_candidates import (
    FinancialCandidateMapping as Mapping, FinancialExtractionCandidate as Candidate,
    FinancialCandidateReview as Review, FinancialCandidateFinalization as Finalization,
    FinancialCandidateTransaction as Link,
)
MAX_REVIEW_EXPORT_RECORDS = 10000


def _json(value):
    if isinstance(value, (UUID, date, datetime)):
        return str(value) if isinstance(value, UUID) else value.isoformat()
    if isinstance(value, dict): return {k:_json(v) for k,v in value.items()}
    if isinstance(value, list): return [_json(v) for v in value]
    return value


def _record(row):
    return {column.name:_json(getattr(row,column.name)) for column in row.__table__.columns}


def capture_pdf_review_history(session, *, case_id, evidence_file_ids):
    remaining = MAX_REVIEW_EXPORT_RECORDS
    def read(statement):
        nonlocal remaining
        values=list(session.scalars(statement.limit(remaining+1)))
        if len(values)>remaining:
            raise LedgerSummaryError('PDF review history exceeds the export limit; no partial history was produced.')
        remaining-=len(values)
        return values
    mappings=[]; candidates=[]; reviews=[]; finalizations=[]; links=[]
    if evidence_file_ids:
        mappings=read(select(Mapping).where(Mapping.case_id==case_id,Mapping.evidence_file_id.in_(evidence_file_ids)).order_by(Mapping.id))
        finalizations=read(select(Finalization).where(Finalization.case_id==case_id,Finalization.evidence_file_id.in_(evidence_file_ids)).order_by(Finalization.id))
    if mappings:
        candidates=read(select(Candidate).where(Candidate.mapping_id.in_([m.id for m in mappings])).order_by(Candidate.mapping_id,Candidate.row_index,Candidate.id))
    if candidates:
        reviews=read(select(Review).where(Review.candidate_id.in_([c.id for c in candidates])).order_by(Review.candidate_id,Review.sequence))
    if finalizations:
        links=read(select(Link).where(Link.finalization_id.in_([f.id for f in finalizations])).order_by(Link.finalization_id,Link.candidate_id))
    for row in [*mappings,*candidates,*finalizations]:
        if _digest(row.snapshot)!=row.snapshot_sha256:
            raise LedgerSummaryError('Stored PDF review original does not match its digest; export refused.')
    events={c.id:[] for c in candidates}
    for review in reviews: events[review.candidate_id].append(review)
    states=[]
    try:
        for candidate in candidates:
            states.append(dict(candidate_id=str(candidate.id),**candidate_review_state(session,candidate=candidate,events=events[candidate.id])))
    except CandidateStoreError as exc:
        raise LedgerSummaryError('Stored PDF review chain is incomplete or inconsistent; export refused.') from exc
    candidate_by_id={c.id:c for c in candidates}; review_by_id={r.id:r for r in reviews}
    counts=Counter(c.mapping_id for c in candidates)
    link_counts=Counter(link.finalization_id for link in links)
    mapping_files={m.id:m.evidence_file_id for m in mappings}
    receipt_files={r.id:r.evidence_file_id for r in finalizations}
    for mapping in mappings:
        if counts[mapping.id]!=mapping.candidate_count:
            raise LedgerSummaryError('PDF mapping candidate coverage is incomplete; export refused.')
    for receipt in finalizations:
        if link_counts[receipt.id]!=receipt.transaction_count:
            raise LedgerSummaryError('PDF finalization transaction coverage is incomplete; export refused.')
    for link in links:
        candidate=candidate_by_id.get(link.candidate_id); review=review_by_id.get(link.review_id)
        if candidate is None or review is None or review.candidate_id!=candidate.id or link.original_sha256!=candidate.snapshot_sha256 or mapping_files[candidate.mapping_id]!=receipt_files[link.finalization_id]:
            raise LedgerSummaryError('PDF finalization links do not match captured review originals; export refused.')
    return dict(schema='loupe.financial.pdf_review_history/1',
        evidence_file_ids=sorted(str(v) for v in evidence_file_ids),
        scope='All saved PDF mappings, candidates, reviews and finalizations for the source files referenced by captured ledger readings. May include other rows from those files; these records do not enter ledger totals.',
        mappings=[_record(v) for v in mappings],candidates=[_record(v) for v in candidates],
        reviews=[_record(v) for v in reviews],review_states=states,
        finalizations=[_record(v) for v in finalizations],transaction_links=[_record(v) for v in links])
