"""Finalize reviewed documentary PDF rows atomically, retaining incomplete coverage."""
from datetime import date
from itertools import combinations
from types import SimpleNamespace
from typing import Annotated
from uuid import UUID

from pydantic import Field, model_validator
from sqlalchemy import or_, select

from postgres.models.case import Case
from postgres.models.enums import ExtractionLayer, LocatorKind, TransactionDirection
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_candidates import (
    FinancialCandidateMapping, FinancialExtractionCandidate,
    FinancialCandidateFinalization, FinancialCandidateTransaction,
)
from services.financial.candidate_assessment import current_candidate_original
from services.financial.candidate_overlap import _claim, _comparison
from services.financial.candidate_reviews import CandidateResolvedReading
from services.financial.candidate_source_bytes import verify_candidate_source_bytes
from services.financial.candidate_store import CandidateStoreError
from services.financial.candidate_statement_scopes import StatementScopesRequest, attach_statement_scopes, record_reviewed_statement_scopes
from services.financial.decisions import Actor
from services.financial.documents import SourceDocumentDraft, record_source_document
from services.financial.locators import Locator, SourceRectangle
from services.financial.pdf_candidates import _Contract, _Digest, _digest
from services.financial.proof_class import SourceShape
from services.financial.references import RowReading
from services.financial.runs import ingestion_run
from services.financial.transactions import TransactionDraft, record_transactions


class CandidateFinalizationRequest(StatementScopesRequest):
    expected_revision: _Digest
    documentary_financial_rows: Annotated[bool, Field(strict=True)]
    accept_incomplete_coverage: Annotated[bool, Field(strict=True)]
    reason: Annotated[str, Field(strict=True, min_length=1, max_length=4096)]

    @model_validator(mode="after")
    def explicit_reason(self):
        if not self.documentary_financial_rows or not self.accept_incomplete_coverage:
            raise ValueError("Explicit documentary-row and incomplete-coverage acceptance is required.")
        if not self.reason.strip():
            raise ValueError("A finalization reason is required.")
        return self


def _request_json(request):
    # Keep old sealed request bodies byte-for-byte comparable when no statement
    # controls were supplied. Existing receipts predate this optional field.
    return request.model_dump(mode="json", exclude={"statement_scopes"} if not request.statement_scopes else set())


def _existing(session, case_id, file_id):
    return session.scalar(select(FinancialCandidateFinalization).where(
        FinancialCandidateFinalization.case_id == case_id,
        FinancialCandidateFinalization.evidence_file_id == file_id))


def _receipt(session, receipt, request=None):
    if _digest(receipt.snapshot) != receipt.snapshot_sha256:
        raise CandidateStoreError("Finalization receipt is inconsistent.")
    if request is not None and receipt.snapshot.get("request") != _request_json(request):
        raise CandidateStoreError("This PDF was finalized with a different request. Use ledger correction history.")
    links = session.execute(select(FinancialCandidateTransaction, FinancialTransaction)
        .join(FinancialTransaction, FinancialTransaction.id == FinancialCandidateTransaction.transaction_id)
        .where(FinancialCandidateTransaction.finalization_id == receipt.id)
        .order_by(FinancialTransaction.row_index)).all()
    if len(links) != receipt.transaction_count or any(
        row.case_id != receipt.case_id or row.source_document_id != receipt.source_document_id
        for _, row in links
    ):
        raise CandidateStoreError("Finalization transaction links are incomplete or inconsistent.")
    return dict(case_id=str(receipt.case_id), evidence_file_id=str(receipt.evidence_file_id),
        finalization_id=str(receipt.id), finalization_revision=receipt.snapshot["request"]["expected_revision"],
        source_document_id=str(receipt.source_document_id),
        run_id=str(receipt.ingestion_run_id), transaction_count=receipt.transaction_count,
        transactions=[dict(candidate_id=str(link.candidate_id), transaction_id=str(row.id),
            ref_id=row.ref_id, superseded_by_id=str(row.superseded_by_id) if row.superseded_by_id else None)
            for link, row in links], proof_class_at_finalization="p3", included_in_default_totals=False,
        applied=True, created=False, limitation="Selected rows only. Incomplete document coverage; later changes use ledger corrections.")


def _source_key(bound, row, typed):
    proposal = bound.proposal
    if proposal.schema_version == "pdf-grid-mapping-v1":
        identity = dict(kind="grid", page=proposal.page_number, table=proposal.table_index, row=typed.row_index)
        order = (proposal.page_number, 0, proposal.table_index, typed.row_index)
    else:
        spans = sorted((cell.source.start_char, cell.source.end_char) for cell in typed.cells)
        identity = dict(kind="text", spans=spans)
        pages = [cell.page_number for cell in typed.cells if cell.page_number is not None]
        order = (min(pages) if pages else 0, 1, spans[0][0], typed.row_index)
    return _digest(dict(evidence_file_id=str(proposal.evidence_file_id), **identity)), order


def _locator(typed, grid):
    if grid:
        rectangles = [cell.locator.rectangle for cell in typed.cells]
        if all(rectangles):
            first = rectangles[0]
            if any((r.page_number, r.page_width, r.page_height) !=
                   (first.page_number, first.page_width, first.page_height) for r in rectangles):
                raise CandidateStoreError("Selected row source rectangles use different pages or dimensions.")
            return Locator(kind=LocatorKind.page_rectangle, rectangle=SourceRectangle(
                page_number=first.page_number, page_width=first.page_width, page_height=first.page_height,
                x0=min(r.x0 for r in rectangles), y0=min(r.y0 for r in rectangles),
                x1=max(r.x1 for r in rectangles), y1=max(r.y1 for r in rectangles)))
        pages = {cell.locator.page for cell in typed.cells}
    else:
        pages = {cell.page_number for cell in typed.cells}
    if len(pages) == 1 and None not in pages:
        return Locator(kind=LocatorKind.page_only, page_number=next(iter(pages)))
    return Locator(kind=LocatorKind.unlocated)


def _prepare(session, *, case_id, evidence_file_id, resolve_path):
    # A case lock also serializes candidate finalizations of two file aliases
    # with identical bytes. Source/review writers already serialize on file.
    if session.scalar(select(Case.id).where(Case.id == case_id).with_for_update(key_share=True)) is None:
        raise CandidateStoreError("Source file not found in this case.", 404)
    source = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
        EvidenceFile.case_id == case_id).with_for_update().execution_options(populate_existing=True))
    if source is None:
        raise CandidateStoreError("Source file not found in this case.", 404)
    existing = _existing(session, case_id, evidence_file_id)
    if existing is not None:
        return existing, None, None, None
    if session.scalar(select(FinancialSourceDocument.id).where(FinancialSourceDocument.case_id == case_id,
        or_(FinancialSourceDocument.evidence_file_id == evidence_file_id,
            FinancialSourceDocument.sha256_at_ingestion == source.sha256)).limit(1)) is not None:
        raise CandidateStoreError("This file or identical source bytes already have a ledger reading.")
    if session.scalar(select(EvidenceDocumentText.evidence_file_id).where(
        EvidenceDocumentText.evidence_file_id == evidence_file_id).with_for_update()) is None:
        raise CandidateStoreError("Candidate source text is missing.", 404)
    session.execute(select(EvidenceTableGeometry.page_number).where(
        EvidenceTableGeometry.evidence_file_id == evidence_file_id)
        .order_by(EvidenceTableGeometry.page_number).with_for_update()).all()
    mappings = list(session.scalars(select(FinancialCandidateMapping).where(
        FinancialCandidateMapping.case_id == case_id, FinancialCandidateMapping.evidence_file_id == evidence_file_id)
        .order_by(FinancialCandidateMapping.id).limit(101)))
    if not mappings or len(mappings) > 100 or sum(m.candidate_count for m in mappings) > 1000:
        raise CandidateStoreError("Finalization requires 1–100 saved batches with at most 1,000 total readings.", 422)
    originals = list(session.scalars(select(FinancialExtractionCandidate).where(
        FinancialExtractionCandidate.mapping_id.in_([m.id for m in mappings]))
        .order_by(FinancialExtractionCandidate.id).with_for_update()))
    by_mapping = {}
    for row in originals:
        by_mapping.setdefault(row.mapping_id, []).append(row)
    all_rows, prepared, claims = [], [], []
    for mapping in mappings:
        rows = by_mapping.get(mapping.id, [])
        if not rows:
            raise CandidateStoreError("Saved mapping is incomplete.")
        saved, _, bound = current_candidate_original(session, case_id=case_id, candidate_id=rows[0].id)
        typed_rows = {row.candidate_key: row for row in bound.candidates}
        for row in saved["candidates"]:
            if row["status"] == "pending":
                raise CandidateStoreError("Resolve or reject every saved reading before finalizing.")
            all_rows.append(dict(candidate_id=row["id"], mapping_id=saved["id"],
                mapping_revision=saved["mapping_revision"], review_revision=row["review_revision"],
                status=row["status"], reading=row["reading"], original_sha256=_digest(row["original"])))
            if row["status"] == "rejected":
                continue
            reading = CandidateResolvedReading.model_validate(row["reading"])
            typed = typed_rows[row["candidate_key"]]
            key, order = _source_key(bound, row, typed)
            claims.append(_claim(saved, row, typed))
            prepared.append(dict(row=row, reading=reading, claim=key, order=order,
                locator=_locator(typed, bound.proposal.schema_version == "pdf-grid-mapping-v1")))
    if not prepared:
        raise CandidateStoreError("At least one resolved financial reading is required.")
    # Complete comparison, bounded by 1,000 candidates (499,500 pairs). Never
    # accept a previously displayed/truncated source-reuse report as a permit.
    if any(_comparison(left, right) is not None for left, right in combinations(claims, 2)):
        raise CandidateStoreError("Selected readings reuse or may overlap source locations. Resolve that before finalizing.")
    accounts = {}
    for account_id in sorted({item["reading"].account_id for item in prepared}, key=str):
        account = session.scalar(select(FinancialAccount).where(FinancialAccount.id == account_id,
            FinancialAccount.case_id == case_id).with_for_update().execution_options(populate_existing=True))
        if account is None:
            raise CandidateStoreError("Reviewed account is missing from this case.")
        accounts[account_id] = account
    for item in prepared:
        reading = item["reading"]
        account = accounts[reading.account_id]
        item["account_label"] = (account.metadata_ or {}).get("display_label") or account.identifier_as_printed or account.holder_name or "Unidentified account"
        provisional_source = (account.metadata_ or {}).get("candidate_account_source_file_id")
        if (account.currency is not None and account.currency != reading.currency) or (
            provisional_source is not None and provisional_source != str(evidence_file_id)):
            raise CandidateStoreError("Reviewed account currency or source PDF changed.")
    verified = verify_candidate_source_bytes(session, case_id=case_id,
        candidate_id=UUID(prepared[0]["row"]["id"]), resolve_path=resolve_path)
    manifest = dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), source_sha256=source.sha256,
        readings=all_rows, accounts=[dict(id=str(key), identity_key=value.identity_key,
            currency=value.currency, provisional_source=(value.metadata_ or {}).get("candidate_account_source_file_id"))
            for key, value in accounts.items()])
    prepared.sort(key=lambda item: (*item["order"], item["row"]["id"]))
    return None, manifest, prepared, verified


def preview_candidate_finalization(session, *, case_id, evidence_file_id, resolve_path, statement_scopes=()):
    """Read-only locked snapshot; caller closes its transaction after display."""
    with session.no_autoflush:
        existing, manifest, prepared, verified = _prepare(session, case_id=case_id,
            evidence_file_id=evidence_file_id, resolve_path=resolve_path)
        if existing is not None:
            return _receipt(session, existing)
        manifest = attach_statement_scopes(session, manifest, prepared, statement_scopes,
            case_id=case_id, evidence_file_id=evidence_file_id)
        return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), applied=False,
            statement_scopes=manifest.get('statement_scopes', []),
            readings=[dict(candidate_id=item['row']['id'], account_id=str(item['reading'].account_id),
                currency=item['reading'].currency, account_label=item['account_label'], booking_date=item['reading'].booking_date,
                transaction_date=item['reading'].transaction_date, description=item['reading'].description)
                for item in prepared],
            revision=_digest(manifest), resolved_count=len(prepared),
            rejected_count=sum(row["status"] == "rejected" for row in manifest["readings"]),
            proof_class="p3", included_in_default_totals=False, file_bytes_verified=True,
            source_sha256=verified["sha256"], byte_count=verified["byte_count"],
            limitation="Selected documentary financial rows only. Whole-file coverage is unverified; finalization prevents later additions.")


def finalize_candidates(*, session_factory, case_id, evidence_file_id, request, actor, resolve_path):
    if not isinstance(actor, Actor):
        raise CandidateStoreError("An identified actor is required.", 422)
    request = CandidateFinalizationRequest.model_validate(request)
    with session_factory() as session:
        if session.scalar(select(EvidenceFile.id).where(EvidenceFile.id == evidence_file_id,
                EvidenceFile.case_id == case_id)) is None:
            raise CandidateStoreError("Source file not found in this case.", 404)
        existing = _existing(session, case_id, evidence_file_id)
        if existing is not None:
            return _receipt(session, existing, request)
    with ingestion_run(case_id=case_id, actor=SimpleNamespace(id=actor.user_id, email=actor.email),
        session_factory=session_factory, config=dict(operation="candidate_materialization",
            evidence_file_id=str(evidence_file_id), request=_request_json(request), actor_name=actor.name)) as run:
        with session_factory() as session:
            try:
                existing, manifest, prepared, verified = _prepare(session, case_id=case_id,
                    evidence_file_id=evidence_file_id, resolve_path=resolve_path)
                if existing is not None:
                    result = _receipt(session, existing, request)
                    session.rollback()
                    return result
                manifest = attach_statement_scopes(session, manifest, prepared, request.statement_scopes,
                    case_id=case_id, evidence_file_id=evidence_file_id)
                if _digest(manifest) != request.expected_revision:
                    raise CandidateStoreError("Saved readings or accounts changed. Reload the finalization preview.")
                snapshot = dict(manifest=manifest, verified_source=verified, request=_request_json(request))
                document = record_source_document(session, run, SourceDocumentDraft(
                    evidence_file_id=evidence_file_id, sha256_at_ingestion=manifest["source_sha256"],
                    document_type="pdf_selected_rows", shape=SourceShape.selected_document_rows,
                    extraction_layer=ExtractionLayer.investigator_review,
                    parser_name="candidate_review", parser_version="1",
                    metadata=dict(coverage="selected_rows_only", finalization_revision=request.expected_revision)))
                period_links, periods = record_reviewed_statement_scopes(session, run, document, request.statement_scopes)
                if periods:
                    snapshot['statement_periods'] = periods
                drafts = []
                for index, item in enumerate(prepared):
                    value = item["reading"]
                    drafts.append(TransactionDraft(row_index=index, account_id=value.account_id,
                        statement_period_id=period_links.get(item['row']['id']),
                        locator=item["locator"], reading=RowReading(currency=value.currency,
                            amount_minor=int(value.amount_minor), direction=TransactionDirection(value.direction),
                            posted_date=date.fromisoformat(value.booking_date) if value.booking_date else None,
                            transaction_date=date.fromisoformat(value.transaction_date) if value.transaction_date else None,
                            value_date=date.fromisoformat(value.value_date) if value.value_date else None,
                            description=value.description), provenance=dict(candidate_id=item["row"]["id"],
                                candidate_original=item["row"]["original"], review_revision=item["row"]["review_revision"])))
                transactions = record_transactions(session, run, document, drafts)
                receipt = FinancialCandidateFinalization(case_id=case_id, evidence_file_id=evidence_file_id,
                    source_document_id=document.id, ingestion_run_id=run.run_id,
                    source_sha256=manifest["source_sha256"], snapshot=snapshot, snapshot_sha256=_digest(snapshot),
                    actor=dict(name=actor.name, email=actor.email, user_id=str(actor.user_id) if actor.user_id else None),
                    reason=request.reason, transaction_count=len(transactions))
                session.add(receipt)
                session.flush()
                for item, row in zip(prepared, transactions):
                    original = item["row"]
                    session.add(FinancialCandidateTransaction(finalization_id=receipt.id,
                        candidate_id=UUID(original["id"]), review_id=UUID(original["history"][-1]["id"]),
                        transaction_id=row.id, source_claim_sha256=item["claim"],
                        review_revision=original["review_revision"], original_sha256=_digest(original["original"])))
                session.flush()
                result = {**_receipt(session, receipt), "created": True}
                session.commit()
                run.document_seen()
                run.transaction_admitted(len(transactions))
                return result
            except Exception:
                session.rollback()
                raise
