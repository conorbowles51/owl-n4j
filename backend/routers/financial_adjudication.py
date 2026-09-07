"""
Financial Adjudication Router - decisions a person takes on the record.

The third financial router, and split from the other two for the reason the
second one gives.  ``routers.financial_ledger`` declares itself read-only and
resolves every route to ``case:view`` on the stated grounds that none of its
routes write; every route here writes, so putting them there would make that
module's docstring false.  ``routers.financial_ingest`` is about reading a bank
file and keeping what it holds, and nothing here keeps anything a file
contains.

What the routes have in common is not their subject but their kind.  Each one
takes a named person's judgement, overrides what the system worked out on its
own, and appends the override to the adjudication log with the grounds and the
name attached.  Two of them do that to a row already in the ledger: quarantine
holds it out of every total, release puts it back.  The third does it to a file
that has not been read yet: the router held it back from the document pipeline,
and admit sends it anyway.

``case:edit`` and not ``evidence:upload``.  Ingest asks for the evidence
permission because it adds evidence to the case.  Nothing is added by any of
these: an existing row is moved out of every total or moved back into them, or
an existing file is sent somewhere it was not going to go.  That is the case's
own content being edited, which is the permission a viewer is denied and an
editor is granted, and it is what ``routers.financial`` already requires to
write to the graph.

No route reverses another's record.  A release does not delete the quarantine
that preceded it; it is appended after it, so the log holds the setting aside,
the grounds, the reversal and the person who took each.  The row itself cannot
hold that history, because
``ck_financial_transactions_quarantine_coherent`` requires a released row to
carry no reason at all.  An admission has no reversal at all, in the log or
anywhere else: ``AdjudicationDecision`` takes no member for one, because it
authorises one send and a send cannot be un-sent.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Literal, Optional
from services.financial.duplicate_decisions import DuplicateDecisionError, decide_duplicate
from services.financial.correction_preview import CorrectionPreviewError, preview_amount_correction
from services.financial.corrections import correct_transaction
from services.financial.quarantine_row import actor_from_user, ActorError
from services.financial.candidate_reviews import CandidateReviewRequest, review_candidate
from services.financial.candidate_store import CandidateStoreError, store_pdf_candidates
from services.financial.pdf_candidates import PdfMappingProposal
from services.financial.pdf_geometry_candidates import PdfGridMapping

from postgres.session import get_db
from routers.case_access import case_access_dependency
from routers.evidence import _resolve_stored_path
from routers.users import get_current_db_user
from services.financial import (
    FileAdmissionOutcome,
    RowAdjudicationOutcome,
    admit_case_file,
    quarantine_case_row,
    release_case_row,
)

logger = logging.getLogger(__name__)


def _adjudication_case_permission(
    request: Request, payload: dict
) -> tuple[str, str] | None:
    # Every route writes or previews a proposed edit. Stated
    # unconditionally rather than per path so that a route added here inherits
    # the write bar, which is the safe direction for a mistake to fall.
    return ("case", "edit")


_require_adjudication_case_access = case_access_dependency(
    _adjudication_case_permission
)


router = APIRouter(
    prefix="/api/financial",
    tags=["financial"],
    dependencies=[
        Depends(get_current_db_user),
        Depends(_require_adjudication_case_access),
    ],
)


@router.post("/candidates/{candidate_id}/review")
async def record_candidate_review(candidate_id: UUID, body: CandidateReviewRequest,
                                  case_id: UUID = Query(...), current_user=Depends(get_current_db_user),
                                  db: Session = Depends(get_db)):
    try:
        return review_candidate(db, case_id=case_id, candidate_id=candidate_id,
                                request=body, actor=actor_from_user(current_user))
    except CandidateStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ActorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("Candidate review failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Candidate review could not be recorded. Reload before retrying.")


@router.post("/candidate-mappings")
async def record_candidate_mapping(body: PdfGridMapping | PdfMappingProposal,
                                   case_id: UUID = Query(...), current_user=Depends(get_current_db_user),
                                   db: Session = Depends(get_db)):
    try:
        return store_pdf_candidates(db, case_id=case_id, proposal=body, actor=actor_from_user(current_user))
    except CandidateStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ActorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("Candidate save failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="PDF readings could not be saved. Reload before retrying.")


def _respond(result) -> dict:
    """Turn one adjudication into a response, erroring only where it must.

    ``not_found`` is a 404 worded the same as a row belonging to another case,
    so that asking cannot be used to learn what a case the caller cannot see
    contains.  ``write_failed`` is a 500 because there is nothing the person
    can do with it and it belongs in the logs.  Everything else -- including a
    refusal -- is a fact about the row's current standing and returns 200
    carrying it, so the interface can put it beside the row rather than in the
    browser's error path.
    """
    if result.outcome is RowAdjudicationOutcome.not_found:
        raise HTTPException(status_code=404, detail=result.reason)
    if result.outcome is RowAdjudicationOutcome.write_failed:
        raise HTTPException(status_code=500, detail=result.reason)
    return result.as_dict()


def _respond_admission(result) -> dict:
    """The same rule applied to a file, against that outcome's own enum.

    Written out a second time rather than folded into :func:`_respond`.  The
    two enums happen to share the names ``not_found`` and ``write_failed``
    today, so a shared helper would have to compare ``outcome.value`` as a
    string and would go on passing if one of them were later renamed on only
    one side.  Comparing by identity against the enum the result actually
    carries fails loudly instead, which is the direction a mistake here should
    fall: the branch it selects decides whether a refusal reaches the
    interface or the browser's error path.

    ``nothing_to_override`` is deliberately not an error.  It means the router
    was not holding the file, so it can be processed with no decision recorded
    at all -- something the caller can act on rather than something that went
    wrong -- and a 4xx would send it down the failure path instead.
    """
    if result.outcome is FileAdmissionOutcome.not_found:
        raise HTTPException(status_code=404, detail=result.reason)
    if result.outcome is FileAdmissionOutcome.write_failed:
        raise HTTPException(status_code=500, detail=result.reason)
    return result.as_dict()


@router.post("/transactions/{transaction_id}/quarantine")
async def quarantine_transaction_row(
    transaction_id: UUID,
    case_id: UUID = Query(..., description="REQUIRED: Case ID"),
    reason: str = Body(
        ...,
        embed=True,
        description=(
            "REQUIRED: why this row is being set aside. Recorded verbatim "
            "against the decision, with the name of whoever took it."
        ),
    ),
    current_user=Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Hold one row out of the ledger's totals on a person's authority.

    The reason is required and not defaulted.  Quarantine removes a row from
    every sum, search and money flow the case reports, so a row set aside with
    no stated grounds leaves a total that is lower than the evidence and
    nothing on the record explaining the difference.  The cost of asking is one
    field. The cost of not asking is a number that cannot be defended.

    The grounds recorded are always ``adjudicated``.  The computed grounds are
    decided against a reconciled period, not against a request, and are not
    reachable from here by design: a class a person raised must not be able to
    pass for one the arithmetic proved.
    """
    result = quarantine_case_row(
        db,
        case_id=case_id,
        transaction_id=transaction_id,
        actor=current_user,
        reason=reason,
    )
    return _respond(result)


@router.post("/transactions/{transaction_id}/release")
async def release_transaction_row(
    transaction_id: UUID,
    case_id: UUID = Query(..., description="REQUIRED: Case ID"),
    reason: str = Body(
        ...,
        embed=True,
        description=(
            "REQUIRED: why this row is being returned to the ledger. Recorded "
            "verbatim against the reversal."
        ),
    ),
    current_user=Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Return one quarantined row to the ledger's totals.

    The reason is required here for a reason the row cannot carry.  A released
    row must have its quarantine reason nulled, so the row afterwards is
    indistinguishable from one that was never set aside; the log is the only
    place that can hold why it was let back in, and a blank there would leave a
    total that changed with nothing saying who changed it.
    """
    result = release_case_row(
        db,
        case_id=case_id,
        transaction_id=transaction_id,
        actor=current_user,
        reason=reason,
    )
    return _respond(result)


@router.post("/files/{file_id}/admit")
async def admit_file_to_document_pipeline(
    file_id: UUID,
    case_id: UUID = Query(..., description="REQUIRED: Case ID"),
    reason: str = Body(
        ...,
        embed=True,
        description=(
            "REQUIRED: why this file should go to the document pipeline "
            "despite what the router found. Recorded verbatim against the "
            "decision, with the name of whoever took it."
        ),
    ),
    current_user=Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Overrule the router on one file, on the record.

    The router looks at every uploaded file and holds back the ones that look
    like bank data, because the document pipeline reads figures out of text
    rather than parsing them, and a number it produced is indistinguishable
    downstream from one that was parsed exactly.  Sometimes it is wrong, or the
    file is a bank file the ledger genuinely cannot use, and someone has to be
    able to say so.  This is where they say it.

    The route takes no description of the file and no statement of what the
    router found.  Both are read from the file again inside
    ``admit_case_file``, immediately before the decision is written, because
    the log's account of what was overruled has to be the file's own and not
    the caller's -- otherwise a request could put any finding it liked into the
    permanent record of a decision.

    This records the decision.  It does not send the file; the caller does
    that afterwards, by the ordinary processing route.  So a 200 here means the
    authority now exists on the record, not that anything has been processed.
    """
    result = admit_case_file(
        db,
        case_id=case_id,
        file_id=file_id,
        actor=current_user,
        reason=reason,
        resolve_path=_resolve_stored_path,
    )
    return _respond_admission(result)


class DuplicateDecisionRequest(BaseModel):
    action: Literal["exclude", "restore"]
    reason: str = Field(min_length=1, max_length=4000)
    expected_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    primary_id: Optional[UUID] = None
    expected_primary_revision: Optional[str] = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class AmountCorrectionPreviewRequest(BaseModel):
    # A decimal string avoids rounding BIGINT money in browser JSON numbers.
    amount_minor: str = Field(strict=True, pattern=r"^(0|[1-9][0-9]{0,18})$")
    direction: Literal["credit", "debit"]


class AmountCorrectionRequest(AmountCorrectionPreviewRequest):
    reason: str = Field(min_length=1, max_length=4000)
    expected_revision: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.post("/transactions/{transaction_id}/correction")
async def record_amount_correction(
    transaction_id: UUID, payload: AmountCorrectionRequest,
    case_id: UUID = Query(...), current_user=Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    try:
        return correct_transaction(db, case_id=case_id, transaction_id=transaction_id,
                                   amount_minor=int(payload.amount_minor), direction=payload.direction,
                                   expected_revision=payload.expected_revision, reason=payload.reason,
                                   actor=actor_from_user(current_user))
    except (CorrectionPreviewError, ActorError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 422), detail=str(exc))
    except Exception:
        logger.exception("Correction failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="The correction could not be confirmed. Refresh before trying again.")


@router.post("/transactions/{transaction_id}/correction-preview")
async def amount_correction_preview(
    transaction_id: UUID, payload: AmountCorrectionPreviewRequest,
    case_id: UUID = Query(...), db: Session = Depends(get_db),
):
    try:
        return preview_amount_correction(db, case_id=case_id, transaction_id=transaction_id,
                                         amount_minor=int(payload.amount_minor), direction=payload.direction)
    except CorrectionPreviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    except Exception:
        logger.exception("Correction preview failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="The correction preview could not be calculated.")
    finally:
        # Release the coherent-snapshot locks and discard any incidental ORM
        # state. A preview must never persist reconciliation or disposition.
        db.rollback()


@router.post("/documents/{document_id}/duplicate-decision")
async def record_duplicate_decision(
    document_id: UUID,
    payload: DuplicateDecisionRequest,
    case_id: UUID = Query(...),
    current_user=Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    try:
        return decide_duplicate(db, case_id=case_id, document_id=document_id,
                                actor=actor_from_user(current_user), **payload.model_dump())
    except (DuplicateDecisionError, ActorError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 422), detail=str(exc))
    except Exception:
        logger.exception("Duplicate decision failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="The decision could not be confirmed. Refresh before trying again.")
