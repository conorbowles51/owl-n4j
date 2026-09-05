"""
Financial Ingest Router - reading a bank file before deciding to store it.

Separate from ``routers.financial_ledger`` on purpose.  That router declares
itself read-only and resolves every route to ``case:view``, on the stated
grounds that none of its routes write.  The endpoints that belong here are the
ones that lead to a write, so putting them there would make that module's own
docstring false the moment the second one lands.

The route below still only reads.  It opens an evidence file, parses it, and
returns what the file says it holds.  It stores nothing, opens no ingestion
run, and leaves no trace on the case.  It is the step before the decision, not
the decision.
"""

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from postgres.session import get_db
from routers.case_access import case_access_dependency
from routers.evidence import _resolve_stored_path
from routers.users import get_current_db_user
from services.financial import PrecheckOutcome, precheck_case_file
from services.financial.native import CenturyWindow, CenturyWindowError

logger = logging.getLogger(__name__)


def _ingest_case_permission(request: Request, payload: dict) -> tuple[str, str] | None:
    # Prechecking reads a file's contents and reports what is in it, so it is
    # gated on being able to see the case, not on being able to add to it.
    #
    # It is a POST because it takes a file and does work, not because it
    # changes anything, so the method is not what decides the permission here.
    # The ingest route that will join this router does write and will need
    # ``evidence:upload``; at that point this resolver has to distinguish the
    # two by path, and returning one pair for everything would silently hand
    # the write route the reader's permission.
    return ("case", "view")


_require_ingest_case_access = case_access_dependency(_ingest_case_permission)


router = APIRouter(
    prefix="/api/financial",
    tags=["financial"],
    dependencies=[
        Depends(get_current_db_user),
        Depends(_require_ingest_case_access),
    ],
)


@router.post("/precheck")
async def precheck_financial_file(
    case_id: UUID = Query(..., description="REQUIRED: Case ID"),
    file_id: UUID = Query(..., description="REQUIRED: Evidence file ID"),
    window_start: date = Query(
        ...,
        description=(
            "REQUIRED: earliest date this matter's evidence may fall in. "
            "Three of the four native bank formats print two-digit years and "
            "none of them carries the century, so the period has to be stated "
            "or the year cannot be resolved."
        ),
    ),
    window_end: date = Query(
        ..., description="REQUIRED: latest date this matter's evidence may fall in"
    ),
    default_currency: str | None = Query(
        None,
        description=(
            "Currency to assume for a format that does not print one. Supplied "
            "rather than guessed, because a wrong guess produces amounts that "
            "look right."
        ),
    ),
    db: Session = Depends(get_db),
):
    """What one native bank file says it holds, without storing any of it.

    The window is required and not defaulted.  A default would decide which
    century a two-digit year names, silently, in the one place where the
    document itself is no help; and a case carries no date range to take one
    from.  The cost of asking is one field on the dialog. The cost of guessing
    is a statement filed under the wrong decade with nothing on the record to
    say so.

    ``outcome`` is the answer, and ``would_ingest`` is a shorthand for one
    value of it.  Neither promises the write will succeed: a period that
    contradicts one already stored is decided against the database, not against
    this file, and cannot be known here.
    """
    try:
        window = CenturyWindow(window_start, window_end)
    except CenturyWindowError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = precheck_case_file(
            db,
            case_id=case_id,
            file_id=file_id,
            resolve_path=_resolve_stored_path,
            window=window,
            default_currency=default_currency,
        )
    except Exception as e:
        logger.error(
            f"Failed to precheck file {file_id} in case {case_id}: {e}"
        )
        raise HTTPException(status_code=500, detail=str(e))

    if result.outcome is PrecheckOutcome.not_found:
        # A file belonging to another case is reported the same way as one that
        # does not exist, so that asking cannot be used to learn what a case the
        # caller cannot see contains.
        raise HTTPException(status_code=404, detail=result.reason)

    # Every other outcome is a description, not an error.  A file that will not
    # parse is a fact about the file that the person needs to see next to the
    # ones that will, and a 4xx here would put it in the browser's error path
    # instead of on the screen.
    return result.as_dict()
