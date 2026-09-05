"""
Financial Reconciliation Router - whether a case's rows add up to its statements.

The fourth financial router.  ``routers.financial_ledger`` returns the rows and
the runs that produced them; this returns the arithmetic over those rows, which
is the only thing in the subsystem that can detect a transaction that is simply
missing.  A dropped row does not arrive flagged as doubtful.  It does not arrive
at all, and the printed closing balance is the only witness to it.

Two routes and two permissions, which is why this is not folded into either
neighbour.  ``routers.financial_ledger`` resolves every route to ``case:view``
on the stated grounds that none of its routes write, and the recompute here
writes.  ``routers.financial_adjudication`` resolves every route to
``case:edit`` on the stated grounds that all of its routes do, and the read here
does not.  Either merge would make an existing module's docstring false.

**The recompute is a POST and the read is a GET, and that split is load
bearing.**  The stored result is the one recorded against the run that produced
it, at the time it was produced.  If a read recomputed, the figure an analyst
quoted would be a figure that no longer exists anywhere, and two people opening
the same case minutes apart could be looking at different arithmetic with
nothing to say which was which.  So the GET reports the column, including when
the column says ``not_attempted``, and re-running is an act someone takes.

**``case:edit`` for the recompute, not ``evidence:upload``.**  Nothing is added
to the case: rows already in the ledger are summed and the answer is written
onto periods already in the ledger.  That is the case's own content being
edited, which is the bar ``routers.financial_adjudication`` already applies for
the same kind of change.

Nothing here moves a proof class.  A document's class is a function of its
source shape and its arithmetic, and moving it on this result is
``assign_proof_class`` and ``record_admission`` in a later unit; two code paths
writing that column on two definitions of the same word is how it would come to
mean neither.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from postgres.models.enums import ReconciliationStatus
from postgres.session import get_db
from routers.case_access import case_access_dependency
from routers.users import get_current_db_user
from services.financial import (
    CaseOutcome,
    ReconciliationQueryError,
    list_period_reconciliations,
    reconcile_case,
    to_reconciliation_view,
)

logger = logging.getLogger(__name__)


def _reconciliation_case_permission(
    request: Request, payload: dict
) -> tuple[str, str] | None:
    """``case:view`` to read the recorded result, ``case:edit`` to recompute it.

    Resolved from the method rather than the path so that a route added to this
    router inherits the bar its verb implies.  A safe-method route can only ever
    read, and anything else is treated as a write whether or not it turns out to
    be one, which is the direction a mistake here should fall.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return ("case", "view")
    return ("case", "edit")


_require_reconciliation_case_access = case_access_dependency(
    _reconciliation_case_permission
)


router = APIRouter(
    prefix="/api/financial",
    tags=["financial"],
    dependencies=[
        Depends(get_current_db_user),
        Depends(_require_reconciliation_case_access),
    ],
)


@router.get("/reconciliation")
async def get_case_reconciliation(
    case_id: UUID = Query(..., description="REQUIRED: Case ID"),
    account_id: UUID | None = Query(None, description="Restrict to one account"),
    reconciliation_status: str | None = Query(
        None,
        description=(
            "Status to filter on: not_attempted, balanced, unbalanced, or "
            "unavailable. Defaults to every status, because a period nobody "
            "has checked is the thing this read exists to surface."
        ),
    ),
    limit: int | None = Query(
        None, description="Return at most this many periods, oldest first"
    ),
    db: Session = Depends(get_db),
):
    """The recorded balance identity for each statement period in one case.

    Reports what is stored and recomputes nothing.  A period that has never
    been checked comes back ``not_attempted`` with null totals, which is the
    honest answer and is deliberately not filtered out of the default: a ledger
    nobody has reconciled must not be able to present itself as a reconciled
    one.

    ``independent`` says whether both balances were printed on the statement
    itself.  An identity computed against a balance carried forward from the
    neighbouring period is arithmetic against that period's figure rather than
    against this document, and it is worth having without being independent
    evidence that this statement was read completely.
    """
    status: ReconciliationStatus | None = None
    if reconciliation_status is not None:
        try:
            status = ReconciliationStatus(reconciliation_status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown reconciliation_status '{reconciliation_status}'. "
                    "Valid values: "
                    f"{', '.join(s.value for s in ReconciliationStatus)}"
                ),
            )

    try:
        rows = list_period_reconciliations(
            db,
            case_id,
            account_id=account_id,
            reconciliation_status=status,
            limit=limit,
        )
    except ReconciliationQueryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list reconciliations for case {case_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    periods = [to_reconciliation_view(row).to_json() for row in rows]
    return {
        "case_id": str(case_id),
        "periods": periods,
        "total": len(periods),
    }


@router.post("/reconciliation/run")
async def run_case_reconciliation(
    case_id: UUID = Query(..., description="REQUIRED: Case ID"),
    account_id: UUID | None = Query(
        None, description="Restrict the sweep to one account"
    ),
    db: Session = Depends(get_db),
):
    """Recompute the balance identity across the case and record the results.

    Safe to run repeatedly.  The identity is a function of the rows currently
    admitted, so re-running it after a row has been quarantined or released is
    exactly how the ledger's arithmetic is kept true to the ledger's contents,
    and re-running it after nothing has changed rewrites the same numbers and a
    new timestamp.

    A period whose stored data will not support the arithmetic is reported
    ``refused`` with the reason, and the sweep continues.  Its previously
    recorded verdict is left untouched rather than reset, because that verdict
    was a real result when it was taken and a failure to re-derive it today is
    not evidence that it was wrong.

    ``applied`` is what an interface should read to decide whether anything
    changed.  The outcome words are a closed vocabulary today and may grow, and
    a caller switching on the word would silently mishandle a member added
    later.
    """
    result = reconcile_case(db, case_id, account_id=account_id)

    if result.outcome is CaseOutcome.write_failed:
        raise HTTPException(status_code=500, detail=result.reason)

    # ``no_periods`` is a 200.  A case that holds no statement periods is a
    # fact about the case, not a failure of the request, and an interface
    # needs to render it beside the ledger rather than in an error path.
    return result.as_dict()
