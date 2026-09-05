"""
Financial Ledger Router - read access to the relational ledger.

``/api/financial`` reads the Neo4j graph that mirrors admitted transactions.
This router reads the other store: the Postgres ledger tables that
``services.financial.transactions.record_transactions`` writes into, and that
nothing before this router could read back out through the API. It is
read-only. Admitting, correcting, or quarantining a row stays with the
ingestion and adjudication services that act with a run and an actor behind
them.

Two reads of the same store, at two levels. ``/ledger`` returns the rows.
``/runs`` returns the executions that produced them, including the ones that
produced nothing because they failed. Both are ``case:view``, and neither
writes, which is what keeps this router's claim about itself true.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from postgres.models.enums import IngestionRunStatus, LedgerStatus
from postgres.session import get_db
from routers.case_access import case_access_dependency
from routers.users import get_current_db_user
from services.financial import (
    LedgerQueryError,
    RunQueryError,
    list_runs,
    list_transactions,
    to_run_view,
    to_view,
)

import logging

logger = logging.getLogger(__name__)


def _ledger_case_permission(request: Request, payload: dict) -> tuple[str, str] | None:
    # Every route on this router reads; none of them write.
    return ("case", "view")


_require_ledger_case_access = case_access_dependency(_ledger_case_permission)


router = APIRouter(
    prefix="/api/financial",
    tags=["financial"],
    dependencies=[
        Depends(get_current_db_user),
        Depends(_require_ledger_case_access),
    ],
)


@router.get("/ledger")
async def get_ledger_transactions(
    case_id: UUID = Query(..., description="REQUIRED: Case ID"),
    account_id: Optional[UUID] = Query(
        None, description="Restrict to one account"
    ),
    ledger_status: Optional[str] = Query(
        None,
        description=(
            "Ledger status to filter on: admitted, quarantined, superseded, "
            "or rejected. Defaults to admitted."
        ),
    ),
    start_date: Optional[date] = Query(
        None, description="Earliest ordering_date, inclusive"
    ),
    end_date: Optional[date] = Query(
        None, description="Latest ordering_date, inclusive"
    ),
    db: Session = Depends(get_db),
):
    """Rows from the relational ledger for one case, defaulting to admitted rows.

    ``ordering_date`` -- not any one of the four printed dates a row may also
    carry -- is what ``start_date``/``end_date`` bound, because it is the
    column the ledger itself orders and reconciles by.
    """
    status: Optional[LedgerStatus] = None
    if ledger_status is not None:
        try:
            status = LedgerStatus(ledger_status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown ledger_status '{ledger_status}'. Valid values: "
                    f"{', '.join(s.value for s in LedgerStatus)}"
                ),
            )

    try:
        rows = list_transactions(
            db,
            case_id,
            account_id=account_id,
            ledger_status=status,
            start_date=start_date,
            end_date=end_date,
        )
    except LedgerQueryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            f"Failed to list ledger transactions for case {case_id}: {e}"
        )
        raise HTTPException(status_code=500, detail=str(e))

    transactions = [to_view(row).to_json() for row in rows]
    return {
        "case_id": str(case_id),
        "transactions": transactions,
        "total": len(transactions),
    }


@router.get("/runs")
async def get_ingestion_runs(
    case_id: UUID = Query(..., description="REQUIRED: Case ID"),
    status: Optional[str] = Query(
        None,
        description=(
            "Run status to filter on: pending, running, completed, failed, "
            "or aborted. Defaults to every status, because a failed run is "
            "the thing this read exists to surface."
        ),
    ),
    limit: Optional[int] = Query(
        None, description="Return at most this many runs, newest first"
    ),
    db: Session = Depends(get_db),
):
    """Ingestion runs for one case, newest first, every status by default.

    Unlike ``/ledger``, which defaults to the admitted population because that
    is what totals are filtered to, this defaults to everything. A run that
    failed or was aborted is precisely what someone asking about a case's
    ledger needs to see, and putting it behind a query parameter would let a
    half-finished ingest stay invisible to anyone who did not already suspect
    it.

    A ``running`` run is reported as running, with the time it started and
    nothing else claimed about it. Whether such a run has in fact been
    abandoned is decided and recorded by the reaper, not guessed at here.
    """
    run_status: Optional[IngestionRunStatus] = None
    if status is not None:
        try:
            run_status = IngestionRunStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown status '{status}'. Valid values: "
                    f"{', '.join(s.value for s in IngestionRunStatus)}"
                ),
            )

    try:
        rows = list_runs(db, case_id, status=run_status, limit=limit)
    except RunQueryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list ingestion runs for case {case_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    runs = [to_run_view(row).to_json() for row in rows]
    return {
        "case_id": str(case_id),
        "runs": runs,
        "total": len(runs),
    }
