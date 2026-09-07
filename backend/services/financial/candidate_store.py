"""Save source-bound originals atomically; never write ledger transactions.

Use a dedicated request session. The writer owns commit/rollback, locks the source
rows and rebinds rather than accepting a caller-built 'bound' result. Review and
materialization are separate future operations. Candidate keys deduplicate the
same mapping snapshot, not overlapping mappings or transactions across revisions.
"""
from copy import deepcopy

from sqlalchemy import or_, select

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceTableGeometry
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialExtractionCandidate, FinancialCandidateReview
from postgres.models.financial import FinancialAccount
from services.financial.decisions import Actor
from services.financial.pdf_candidates import PdfMappingError, PdfMappingProposal, _digest, bind_pdf_mapping
from services.financial.pdf_geometry_candidates import PdfGridMapping, bind_pdf_grid_mapping


class CandidateStoreError(ValueError):
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


def list_candidate_mappings(session, *, case_id, limit=25, offset=0):
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise CandidateStoreError("Invalid candidate list page.", 422)
    rows = session.execute(select(FinancialCandidateMapping, EvidenceFile.original_filename)
        .join(EvidenceFile, EvidenceFile.id == FinancialCandidateMapping.evidence_file_id)
        .where(FinancialCandidateMapping.case_id == case_id, EvidenceFile.case_id == case_id)
        .order_by(FinancialCandidateMapping.created_at.desc(), FinancialCandidateMapping.id.desc())
        .offset(offset).limit(limit+1)).all()
    return dict(case_id=str(case_id), offset=offset, has_more=len(rows)>limit,
        items=[dict(id=str(row.id), evidence_file_id=str(row.evidence_file_id), filename=filename,
            candidate_count=row.candidate_count, created_at=row.created_at.isoformat()) for row, filename in rows[:limit]])


def list_candidate_accounts(session, *, case_id, search="", limit=100):
    if not isinstance(search, str) or len(search)>128 or type(limit) is not int or not 1 <= limit <= 100:
        raise CandidateStoreError("Invalid account search.", 422)
    query = select(FinancialAccount).where(FinancialAccount.case_id == case_id)
    if search.strip():
        query = query.where(or_(*(field.icontains(search.strip(), autoescape=True) for field in (
            FinancialAccount.identifier_as_printed, FinancialAccount.holder_name, FinancialAccount.institution_name))))
    rows = list(session.scalars(query.order_by(FinancialAccount.id).limit(limit+1)))
    return dict(case_id=str(case_id), has_more=len(rows)>limit,
        items=[dict(id=str(row.id), identifier=row.identifier_as_printed, holder=row.holder_name,
                    institution=row.institution_name, currency=row.currency) for row in rows[:limit]])


def read_candidate_mapping(session, *, case_id, mapping_id):
    from services.financial.candidate_reviews import candidate_review_state
    mapping = session.scalar(select(FinancialCandidateMapping).where(
        FinancialCandidateMapping.id == mapping_id, FinancialCandidateMapping.case_id == case_id))
    if mapping is None:
        raise CandidateStoreError("Candidate mapping not found in this case.", 404)
    rows = list(session.scalars(select(FinancialExtractionCandidate).where(
        FinancialExtractionCandidate.mapping_id == mapping.id).order_by(FinancialExtractionCandidate.row_index)))
    if (len(rows) != mapping.candidate_count or _digest(mapping.snapshot) != mapping.snapshot_sha256
            or any(_digest(row.snapshot) != row.snapshot_sha256 for row in rows)):
        raise CandidateStoreError("Stored candidate originals are incomplete or inconsistent.")
    events = list(session.scalars(select(FinancialCandidateReview)
        .join(FinancialExtractionCandidate, FinancialExtractionCandidate.id == FinancialCandidateReview.candidate_id)
        .where(FinancialExtractionCandidate.mapping_id == mapping.id).order_by(FinancialCandidateReview.sequence)))
    by_candidate = {row.id: [] for row in rows}
    for event in events:
        by_candidate[event.candidate_id].append(event)
    return dict(id=str(mapping.id), case_id=str(mapping.case_id), evidence_file_id=str(mapping.evidence_file_id),
        mapping_revision=mapping.mapping_revision, original=deepcopy(mapping.snapshot),
        actor=deepcopy(mapping.actor), created_at=mapping.created_at.isoformat(),
        candidates=[dict(id=str(row.id), candidate_key=row.candidate_key, row_index=row.row_index,
                         **candidate_review_state(session, candidate=row, events=by_candidate[row.id]),
                         original=deepcopy(row.snapshot)) for row in rows], applied=False)


def store_pdf_candidates(session, *, case_id, proposal, actor):
    if not isinstance(actor, Actor):
        raise CandidateStoreError("A recorded actor is required.", 422)
    if session.new or session.dirty or session.deleted:
        raise CandidateStoreError("Use a clean, dedicated session to save candidates.", 422)
    if isinstance(proposal, (PdfMappingProposal, PdfGridMapping)):
        proposal = proposal.model_dump(mode="json")
    if not isinstance(proposal, dict):
        raise CandidateStoreError("A source mapping proposal is required.", 422)
    grid = proposal.get("schema_version") == "pdf-grid-mapping-v1"
    validated = (PdfGridMapping if grid else PdfMappingProposal).model_validate(proposal)
    if validated.case_id != case_id:
        raise CandidateStoreError("Mapping does not belong to this case.", 404)
    try:
        # Serialize saves per file, including different candidate mapping kinds.
        file_id = session.scalar(select(EvidenceFile.id).where(
            EvidenceFile.id == validated.evidence_file_id, EvidenceFile.case_id == case_id).with_for_update())
        if file_id is None:
            raise CandidateStoreError("Source file not found in this case.", 404)
        text_id = session.scalar(select(EvidenceDocumentText.evidence_file_id).where(
            EvidenceDocumentText.evidence_file_id == file_id).with_for_update())
        if text_id is None:
            raise CandidateStoreError("Source text not found in this case.", 404)
        if grid:
            geometry_id = session.scalar(select(EvidenceTableGeometry.evidence_file_id).where(
                EvidenceTableGeometry.evidence_file_id == file_id,
                EvidenceTableGeometry.page_number == validated.page_number).with_for_update())
            if geometry_id is None:
                raise CandidateStoreError("Stored table source not found in this case.", 404)
        bound = (bind_pdf_grid_mapping if grid else bind_pdf_mapping)(session, case_id=case_id, proposal=validated)
        original = bound.model_dump(mode="json")
        candidates = original.pop("candidates")
        existing = session.scalar(select(FinancialCandidateMapping).where(
            FinancialCandidateMapping.case_id == case_id, FinancialCandidateMapping.evidence_file_id == file_id,
            FinancialCandidateMapping.mapping_revision == bound.mapping_revision))
        if existing is not None:
            if existing.snapshot != original:
                raise CandidateStoreError("Existing mapping original does not match the source binding.")
            result = read_candidate_mapping(session, case_id=case_id, mapping_id=existing.id)
            if [c["original"] for c in result["candidates"]] != candidates:
                raise CandidateStoreError("Existing candidate originals do not match the source binding.")
            session.commit()
            return {**result, "created": False}
        mapping = FinancialCandidateMapping(case_id=case_id, evidence_file_id=file_id,
            mapping_revision=bound.mapping_revision, snapshot=original, snapshot_sha256=_digest(original),
            candidate_count=len(candidates), actor=dict(name=actor.name, email=actor.email,
                user_id=str(actor.user_id) if actor.user_id is not None else None))
        session.add(mapping)
        session.flush()
        for candidate in candidates:
            session.add(FinancialExtractionCandidate(mapping_id=mapping.id,
                candidate_key=candidate["candidate_key"], row_index=candidate["row_index"],
                snapshot=candidate, snapshot_sha256=_digest(candidate)))
        session.flush()
        result = read_candidate_mapping(session, case_id=case_id, mapping_id=mapping.id)
        session.commit()
        return {**result, "created": True}
    except PdfMappingError as exc:
        session.rollback()
        raise CandidateStoreError(str(exc), exc.status_code) from exc
    except Exception:
        session.rollback()
        raise
