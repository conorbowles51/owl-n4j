"""
Financial Ledger Router - read access to the relational ledger.

``/api/financial`` reads the Neo4j graph that mirrors admitted transactions.
This router reads the other store: the Postgres ledger tables that
``services.financial.transactions.record_transactions`` writes into, and that
nothing before this router could read back out through the API. It is
read-only. Admitting, correcting, or quarantining a row stays with the
ingestion and adjudication services that act with a run and an actor behind
them.

Reads of the same store at several levels. ``/ledger`` returns the rows.
``/runs`` returns the executions that produced them, including the ones that
produced nothing because they failed. ``/decisions`` returns what was decided
about any of it, by whom, and when. ``/proof-standing`` returns how much of the
case's evidence sits in each proof class and what each of those classes is
allowed to do. ``/duplicates`` compares current stored readings and reports
actual document dispositions. All reads are ``case:view`` and none writes, which is
what keeps this router's claim about itself true.

``/decisions`` is here rather than on ``routers.financial_adjudication``, where
the two routes that *write* those records live, and the reason is that router's
own comment: it resolves every route to ``case:edit`` unconditionally so that
anything added there inherits the write bar. A read dropped in would take a
permission it does not need, and would make that comment false. Reading a
history is ``case:view`` in the same sense that reading the rows is, so it
belongs with the reads.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field
from services.financial.amount_assessment import AmountAssessmentError, assess_source_amount

from postgres.models.enums import (
    AdjudicationDecision,
    AdjudicationSubject,
    IngestionRunStatus,
    LedgerStatus,
)
from postgres.session import get_db
from routers.case_access import case_access_dependency
from routers.users import get_current_db_user
from services.financial import (
    DEFAULT_DECISION_LIMIT,
    DecisionLogError,
    LedgerQueryError,
    RunQueryError,
    case_proof_standing,
    list_case_decisions,
    list_runs,
    list_transactions,
    to_run_view,
    to_view,
)

from services.financial.duplicate_query import (
    DuplicateQueryLimitError, list_duplicate_candidates,
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


class AmountAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_char: int = Field(ge=0, strict=True)
    end_char: int = Field(gt=0, strict=True)
    expected_text: str = Field(min_length=1, max_length=128, strict=True)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")


@router.post("/source-files/{evidence_file_id}/amount-assessment")
async def assess_evidence_amount(
    evidence_file_id: UUID,
    body: AmountAssessmentRequest,
    case_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    """Read-only review; origin comes from stored provenance, never the caller."""
    try:
        return assess_source_amount(db, case_id=case_id, evidence_file_id=evidence_file_id,
                                    **body.model_dump())
    except AmountAssessmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Source amount assessment failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Source amount assessment failed.")


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


def _parsed_member(value: Optional[str], enum, field: str):
    """One query string turned into a member of a closed vocabulary, or a 400.

    The two routes above inline this. It is factored out here because this
    route parses two vocabularies rather than one, and because the wording of
    the refusal is the part that matters: naming the valid values in the detail
    is what stops a caller having to guess which of three plausible spellings
    of a decision this table uses. They are not rewritten to use it, because
    changing a working route to save four lines is churn on a path with tests
    already pinned to it.
    """
    if value is None:
        return None
    try:
        return enum(value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown {field} '{value}'. Valid values: "
                f"{', '.join(member.value for member in enum)}"
            ),
        )


@router.get("/decisions")
async def get_case_decisions(
    case_id: UUID = Query(..., description="REQUIRED: Case ID"),
    subject_type: Optional[str] = Query(
        None,
        description=(
            "Restrict to decisions about one kind of subject: transaction, "
            "statement_period, source_document, account, or evidence_file."
        ),
    ),
    subject_id: Optional[UUID] = Query(
        None,
        description=(
            "Restrict to decisions about one subject. Scoped to the case "
            "regardless: a subject in another matter returns nothing."
        ),
    ),
    decision: Optional[str] = Query(
        None, description="Restrict to one kind of decision"
    ),
    limit: int = Query(
        DEFAULT_DECISION_LIMIT,
        description=(
            "Return at most this many decisions, newest first. A limit above "
            "the cap is capped rather than refused, and the response says "
            "which limit was applied."
        ),
    ),
    offset: int = Query(0, description="Skip this many decisions"),
    db: Session = Depends(get_db),
):
    """What has been decided in one case, newest first.

    The adjudication log is append-only and has had writers since quarantine
    landed. This is the first thing that reads it back at the level anyone
    actually asks about it: not "what happened to this row", which
    ``decisions.history`` already answered for one loaded subject, but what has
    been done to the evidence in this matter, by whom, and when.

    Every record says whether a person or the reconciliation stage decided it.
    That distinction is derived from the actor's address by the service and is
    not a filter here, because a caller who wants only one of the two can say
    so with ``decision`` -- ``reclassify_document`` is the only member a
    machine writes -- and a boolean query parameter over a derived field would
    be a second definition of the same fact.

    **The page is bounded and says so.** ``total`` counts every decision
    matching the same filters, and ``truncated`` says whether any were left
    off. A history that quietly stops is worse than no history, which is why
    neither figure is optional.

    ``limit`` and ``offset`` are validated by the service rather than by
    ``Query``, and deliberately: a bound declared twice drifts, and the
    service's rules are not the ones ``Query`` would express. A limit over the
    cap is capped and answered, not refused, so a ``le=`` here would turn a
    served request into a 422. A limit below 1 is refused, and comes back as a
    400 carrying the service's own words for why.
    """
    subject = _parsed_member(subject_type, AdjudicationSubject, "subject_type")
    kind = _parsed_member(decision, AdjudicationDecision, "decision")

    try:
        page = list_case_decisions(
            db,
            case_id,
            subject_type=subject,
            subject_id=subject_id,
            decision=kind,
            limit=limit,
            offset=offset,
        )
    except DecisionLogError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list decisions for case {case_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return page.as_dict()


@router.get("/proof-standing")
async def get_case_proof_standing(
    case_id: UUID = Query(..., description="REQUIRED: Case ID"),
    db: Session = Depends(get_db),
):
    """How this case's evidence stands by proof class, and what each licenses.

    Every class is returned, including the ones holding nothing, with the
    document and row counts carrying that class and the four things
    ``services.financial.proof_class`` says the class permits. The counts and
    the permissions travel together because a figure against ``p3`` tells a
    reader nothing on its own: the label does not say that p3 is the one class
    no run admits by itself, and a reader who guesses wrong shows unadjudicated
    material as though it were verified.

    **No filters.** The other three reads here narrow by status, date or
    subject; this one deliberately takes nothing but the case. It is a census,
    so a filtered census would be a different and smaller claim wearing the
    same name, and the per-class figures would stop adding up to the case's
    documents and rows -- which is the one property that makes the breakdown
    checkable.

    The set of classes counted toward totals is not a query parameter either.
    It is the set the ledger's own aggregates use, and it is reported back in
    ``counted_classes`` so any figure derived from this census can state its
    coverage. Letting a caller choose a different set would let the interface
    display a coverage the totals beside it were never computed against.

    A ``ProofStandingError`` is not translated to a 400 here, unlike
    ``DecisionLogError`` above, and the difference is who can act on it. The
    decision log refuses things a caller sent -- a negative offset, an unknown
    filter -- and the caller can send something else. This route sends the
    service nothing but a case, so the only way it can refuse is a stored
    ``proof_class`` outside the vocabulary, which no request caused and no
    request can fix. That belongs in the logs as a 500.
    """
    try:
        standing = case_proof_standing(db, case_id)
    except Exception as e:
        logger.error(f"Failed to read proof standing for case {case_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return standing.as_dict()


@router.get("/duplicates")
async def get_duplicate_candidates(
    case_id: UUID = Query(..., description="REQUIRED: Case ID"),
    db: Session = Depends(get_db),
):
    """Fresh candidates and actual dispositions; viewing never changes totals."""
    try:
        return list_duplicate_candidates(db, case_id)
    except DuplicateQueryLimitError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("Failed to compare financial documents for case %s", case_id)
        raise HTTPException(status_code=500, detail="Duplicate comparison could not be completed.")
