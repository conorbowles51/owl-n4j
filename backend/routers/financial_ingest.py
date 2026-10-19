"""
Financial Ingest Router - reading a bank file, and storing what it holds.

Separate from ``routers.financial_ledger`` on purpose.  That router declares
itself read-only and resolves every route to ``case:view``, on the stated
grounds that none of its routes write.  The endpoints that belong here are the
ones that lead to a write, so putting them there would make that module's own
docstring false the moment the second one lands.

Two routes, and they are the same reading twice.  ``/precheck`` opens an
evidence file, parses it, and returns what the file says it holds, storing
nothing and leaving no trace on the case.  ``/ingest`` does that reading again
and keeps it: a run is opened, the document, its accounts, its periods and its
rows are written, and the run is terminated either way.

They read through the same functions on purpose.  A precheck that said one
thing and an ingest that said another about the same bytes would make the
dialog worse than useless, since its whole job is to show what is about to
happen.  What ingest can find that precheck cannot is named separately in
:class:`~services.financial.native_ingest_file.IngestOutcome`, and every one of
those is a fact decidable only against rows already stored.
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
from services.financial import (
    IngestOutcome,
    PrecheckOutcome,
    ingest_case_file,
    precheck_case_file,
)
from services.financial.native import CenturyWindow, CenturyWindowError

logger = logging.getLogger(__name__)


#: The paths on this router that only read.  Prechecking reads a file's
#: contents and reports what is in it, so it is gated on being able to see the
#: case, not on being able to add to it.  It is a POST because it takes a file
#: and does work, not because it changes anything, so the method cannot be what
#: decides the permission here.
#:
#: Named as an allow-list rather than the write paths being named, so that a
#: route added to this router without touching this resolver is treated as a
#: write and gated at the higher bar.  The other way round, the new route would
#: silently inherit the reader's permission, and a mistake that hands a writer
#: ``case:view`` is not one the tests would notice.
_READ_ONLY_PATHS = frozenset({"/api/financial/precheck"})


def _ingest_case_permission(request: Request, payload: dict) -> tuple[str, str] | None:
    if request.url.path in _READ_ONLY_PATHS:
        return ("case", "view")
    return ("evidence", "upload")


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


@router.post("/ingest")
async def ingest_financial_file(
    case_id: UUID = Query(..., description="REQUIRED: Case ID"),
    file_id: UUID = Query(..., description="REQUIRED: Evidence file ID"),
    window_start: date = Query(
        ...,
        description=(
            "REQUIRED: earliest date this matter's evidence may fall in. Same "
            "field, same reason, as on precheck: three of the four native bank "
            "formats print two-digit years and none carries the century."
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
    document_type: str | None = Query(
        None, description="Overrides the format's own name on the stored document."
    ),
    institution_name: str | None = Query(
        None,
        description=(
            "The bank, where the file does not name it. Recorded as given and "
            "not inferred from an account number."
        ),
    ),
    current_user=Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Read one native bank file and store what it holds, under a recorded run.

    The same reading ``/precheck`` performs, kept.  A caller that prechecked
    first and got ``readable`` should expect ``stored`` here, but is not
    promised it: the two outcomes precheck cannot reach are decided against
    rows already in the ledger rather than against these bytes, and no amount
    of reading the file would have found them.

    ``outcome`` is the answer and every value of it is documented on
    :class:`~services.financial.native_ingest_file.IngestOutcome`.  Only two
    become error statuses.  A file the caller may not see is a 404, worded the
    same as a file that does not exist so that asking cannot be used to learn
    what another case contains.  A write that failed for a reason that is not
    about the evidence is a 500, because there is nothing the person can do
    with it and it belongs in the logs.  Everything else -- a file that will
    not parse, rows that name an account the document never introduced, a
    period contradicting one already stored, a file this case already holds --
    is a fact about the evidence and returns 200 carrying it, so the interface
    can put it on the screen beside the files that went in.
    """
    try:
        window = CenturyWindow(window_start, window_end)
    except CenturyWindowError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = ingest_case_file(
            db,
            case_id=case_id,
            file_id=file_id,
            resolve_path=_resolve_stored_path,
            window=window,
            default_currency=default_currency,
            document_type=document_type,
            institution_name=institution_name,
            actor=current_user,
        )
    except Exception as e:
        # The service returns rather than raises for everything the evidence
        # can cause, so anything arriving here is a fault.  The rollback is the
        # service's on every path it owns; this one is ours because the session
        # is left mid-transaction by whatever got past it.
        db.rollback()
        logger.exception(
            "Failed to ingest file %s in case %s", file_id, case_id
        )
        raise HTTPException(status_code=500, detail=str(e))

    if result.outcome is IngestOutcome.not_found:
        raise HTTPException(status_code=404, detail=result.reason)

    if result.outcome is IngestOutcome.write_failed:
        # Already logged with its traceback by the service.  The detail is
        # carried through because a constraint name is the fastest route to the
        # cause, and this endpoint is reachable only by a user of the case.
        raise HTTPException(status_code=500, detail=result.reason)

    return result.as_dict()
