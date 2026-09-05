"""
Financial Adjudication Router - changing what a stored ledger row counts as.

The third financial router, and split from the other two for the reason the
second one gives.  ``routers.financial_ledger`` declares itself read-only and
resolves every route to ``case:view`` on the stated grounds that none of its
routes write; both routes here write, so putting them there would make that
module's docstring false.  ``routers.financial_ingest`` is about reading a bank
file and keeping what it holds, and these routes read no file at all.  What
they change is the standing of a row already in the ledger, months after the
file it came from was read.

``case:edit`` and not ``evidence:upload``.  Ingest asks for the evidence
permission because it adds evidence to the case.  Nothing is added here: an
existing row is moved out of every total, or moved back into them.  That is the
case's own content being edited, which is the permission a viewer is denied and
an editor is granted, and it is what ``routers.financial`` already requires to
write to the graph.

Neither route reverses the other's record.  A release does not delete the
quarantine that preceded it; it is appended after it, so the log holds the
setting aside, the grounds, the reversal and the person who took each.  The row
itself cannot hold that history, because
``ck_financial_transactions_quarantine_coherent`` requires a released row to
carry no reason at all.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from postgres.session import get_db
from routers.case_access import case_access_dependency
from routers.users import get_current_db_user
from services.financial import (
    RowAdjudicationOutcome,
    quarantine_case_row,
    release_case_row,
)

logger = logging.getLogger(__name__)


def _adjudication_case_permission(
    request: Request, payload: dict
) -> tuple[str, str] | None:
    # Every route on this router writes; none of them only read.  Stated
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
