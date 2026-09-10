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
from typing import Optional, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field
from services.financial.amount_assessment import AmountAssessmentError, assess_source_amount, read_amount_source_text
from services.financial.ledger_source import LedgerSourceError, ledger_source, statement_source
from services.financial.candidate_store import CandidateStoreError, read_candidate_mapping, list_candidate_mappings, list_candidate_accounts
from services.financial.candidate_assessment import assess_candidate_amounts, assess_candidate_dates
from services.financial.candidate_reviews import read_candidate_review
from services.financial.candidate_overlap import check_candidate_source_reuse
from services.financial.candidate_materialization import preview_candidate_finalization
from services.financial.candidate_statement_scopes import StatementScopesRequest
from routers.evidence import _resolve_stored_path
from services.financial.ledger_snapshot import capture_ledger_export, ledger_export_archive
from services.financial.ledger_summary import ledger_summary, LedgerSummaryError
from services.financial.statement_balances import capture_statement_running_balances
from services.financial.statement_checks import capture_statement_checks, StatementCheckError
from services.financial.coverage_query import requested_statement_coverage, CoverageQueryError, list_statement_coverage
from services.financial.candidate_sources import list_candidate_sources, read_candidate_source
from services.financial.pdf_candidates import PdfMappingError

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


class CandidateAmountAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currency: str = Field(pattern=r"^[A-Z]{3}$", strict=True)


@router.get("/candidates/{candidate_id}/review")
async def get_candidate_review(candidate_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return read_candidate_review(db, case_id=case_id, candidate_id=candidate_id)
    except CandidateStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Candidate review lookup failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Candidate review could not be read.")


@router.get("/candidate-mappings/{mapping_id}")
async def get_candidate_mapping(mapping_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return read_candidate_mapping(db, case_id=case_id, mapping_id=mapping_id)
    except CandidateStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Candidate mapping lookup failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Candidate mapping could not be read.")


@router.get("/candidate-mappings")
async def get_candidate_mappings(case_id: UUID = Query(...), limit: int = Query(25, ge=1, le=100),
                                  offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    try:
        return list_candidate_mappings(db, case_id=case_id, limit=limit, offset=offset)
    except CandidateStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Candidate list failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Saved PDF readings could not be listed.")


from services.financial.ledger_tracing import LedgerTraceInput, ledger_trace_inputs, evaluate_ledger_trace
from services.financial.tracing import TracingError


@router.get("/ledger-trace-inputs")
def get_ledger_trace_inputs(case_id: UUID = Query(...), account_id: UUID = Query(...),
        start_date: date = Query(...), end_date: date = Query(...), population: str = Query("verified"), db: Session = Depends(get_db)):
    try:
        return ledger_trace_inputs(capture_ledger_export(db.get_bind(), case_id=case_id,
            account_id=account_id, start_date=start_date, end_date=end_date), population=population)
    except (LedgerSummaryError, TracingError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("Tracing input capture failed")
        raise HTTPException(status_code=500, detail="Tracing inputs could not be captured.")


@router.post("/ledger-trace")
def run_ledger_trace(body: LedgerTraceInput, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        captured = capture_ledger_export(db.get_bind(), case_id=case_id, account_id=body.account_id,
            start_date=body.start_date, end_date=body.end_date)
        return evaluate_ledger_trace(captured, body)
    except (LedgerSummaryError, TracingError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("Conditional tracing failed")
        raise HTTPException(status_code=500, detail="Tracing scenario could not be calculated.")


@router.get("/ledger-export")
def download_ledger_export(case_id: UUID = Query(...), account_id: Optional[UUID] = Query(None),
        start_date: Optional[date] = Query(None), end_date: Optional[date] = Query(None), db: Session = Depends(get_db), include_source_files: bool = False):
    try:
        source_options = dict(include_source_files=True, resolve_path=_resolve_stored_path) if include_source_files else {}
        exported=capture_ledger_export(db.get_bind(),case_id=case_id,account_id=account_id,
            start_date=start_date,end_date=end_date,**source_options)
        return Response(content=ledger_export_archive(exported),media_type="application/zip",headers={
            "Content-Disposition": 'attachment; filename="loupe-ledger-export.zip"',
            "Cache-Control": "no-store", "X-Loupe-Source-Files": "true" if include_source_files else "false", "X-Content-Type-Options": "nosniff",
            "X-Loupe-Case-Id": str(case_id), "X-Loupe-Account-Id": str(account_id) if account_id else "",
            "X-Loupe-Start-Date": start_date.isoformat() if start_date else "",
            "X-Loupe-End-Date": end_date.isoformat() if end_date else ""})
    except LedgerSummaryError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    except Exception:
        logger.exception("Ledger export failed for case %s",case_id)
        raise HTTPException(status_code=500,detail="Ledger export could not be prepared.")


@router.get("/ledger-counterparties")
async def get_ledger_counterparties(case_id: UUID = Query(...), account_id: Optional[UUID] = Query(None),
        start_date: Optional[date] = Query(None), end_date: Optional[date] = Query(None), db: Session = Depends(get_db)):
    from services.financial.ledger_summary import ledger_counterparties
    try:
        return ledger_counterparties(db, case_id=case_id, account_id=account_id, start_date=start_date, end_date=end_date)
    except LedgerSummaryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("Ledger counterparty summary failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Ledger counterparty summary could not be calculated.")


@router.get("/ledger-trends")
async def get_ledger_trends(case_id: UUID = Query(...), account_id: Optional[UUID] = Query(None),
        start_date: Optional[date] = Query(None), end_date: Optional[date] = Query(None),
        grouping: Literal["daily", "monthly"] = Query("monthly"), db: Session = Depends(get_db)):
    try:
        return ledger_summary(db, case_id=case_id, account_id=account_id, start_date=start_date,
            end_date=end_date, grouping=grouping)
    except LedgerSummaryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("Ledger trends failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Ledger trends could not be calculated.")


@router.get("/ledger-working-analysis")
async def get_working_ledger_analysis(case_id: UUID = Query(...), account_id: Optional[UUID] = Query(None),
        start_date: Optional[date] = Query(None), end_date: Optional[date] = Query(None),
        grouping: Literal["daily", "monthly", "counterparty"] = Query("monthly"), db: Session = Depends(get_db)):
    from services.financial.working_totals import working_ledger_analysis
    try:
        return working_ledger_analysis(db, case_id=case_id, account_id=account_id,
            start_date=start_date, end_date=end_date, grouping=grouping)
    except LedgerSummaryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("Working ledger analysis failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Working analysis could not be calculated.")


@router.get("/ledger-working-summary")
async def get_working_ledger_summary(case_id: UUID = Query(...), account_id: Optional[UUID] = Query(None),
        start_date: Optional[date] = Query(None), end_date: Optional[date] = Query(None),
        db: Session = Depends(get_db)):
    from services.financial.working_totals import working_ledger_summary
    try:
        return working_ledger_summary(db, case_id=case_id, account_id=account_id, start_date=start_date, end_date=end_date)
    except LedgerSummaryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("Working ledger summary failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Working totals could not be calculated.")


@router.get("/ledger-summary")
async def get_ledger_summary(case_id: UUID = Query(...), account_id: Optional[UUID] = Query(None),
        start_date: Optional[date] = Query(None), end_date: Optional[date] = Query(None),
        db: Session = Depends(get_db)):
    try:
        return ledger_summary(db, case_id=case_id, account_id=account_id, start_date=start_date, end_date=end_date)
    except LedgerSummaryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("Ledger summary failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Ledger summary could not be calculated.")


@router.get("/requested-statement-coverage")
async def get_requested_statement_coverage(case_id: UUID = Query(...), account_id: UUID = Query(...),
        start_date: date = Query(...), end_date: date = Query(...), db: Session = Depends(get_db)):
    try:
        return requested_statement_coverage(db, case_id=case_id, account_id=account_id,
            start_date=start_date, end_date=end_date)
    except CoverageQueryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Requested statement coverage failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Requested statement coverage could not be calculated.")


@router.get("/statement-periods/{period_id}/running-balances")
async def get_statement_running_balances(period_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return capture_statement_running_balances(db.get_bind(), case_id=case_id, period_id=period_id)
    except StatementCheckError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("Running-balance check failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Running balances could not be checked.")


@router.get("/statement-periods/{period_id}/source")
async def get_statement_source(period_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return statement_source(db, case_id=case_id, period_id=period_id)
    except LedgerSourceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    except Exception:
        logger.exception("Statement source read failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Statement source could not be read.")


@router.get("/statement-checks")
async def get_statement_checks(case_id: UUID = Query(...), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    try:
        return capture_statement_checks(db.get_bind(), case_id=case_id, offset=offset)
    except StatementCheckError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("Statement balance check failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Statement balances could not be checked.")


@router.get("/statement-coverage")
async def get_statement_coverage(case_id: UUID = Query(...), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    try:
        return list_statement_coverage(db, case_id=case_id, offset=offset)
    except CoverageQueryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Statement coverage failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Statement coverage could not be calculated.")


@router.get("/ledger-accounts")
async def get_candidate_accounts(case_id: UUID = Query(...), search: str = Query("", max_length=128),
                                  db: Session = Depends(get_db)):
    try:
        return list_candidate_accounts(db, case_id=case_id, search=search)
    except CandidateStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Candidate account list failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Ledger accounts could not be listed.")


@router.get("/candidates/{candidate_id}/source-readings")
async def get_candidate_source_readings(candidate_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    from services.financial.candidate_assessment import candidate_source_readings
    try:
        return candidate_source_readings(db, case_id=case_id, candidate_id=candidate_id)
    except CandidateStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Candidate source reading failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Original source readings could not be loaded.")


@router.get("/candidates/{candidate_id}/date-assessment")
async def assess_saved_candidate_dates(candidate_id: UUID, case_id: UUID = Query(...),
                                       db: Session = Depends(get_db)):
    try:
        return assess_candidate_dates(db, case_id=case_id, candidate_id=candidate_id)
    except CandidateStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Candidate date assessment failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Candidate date assessment could not be completed.")


@router.post("/candidates/{candidate_id}/amount-assessment")
async def assess_saved_candidate(candidate_id: UUID, body: CandidateAmountAssessmentRequest,
                                 case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return assess_candidate_amounts(db, case_id=case_id, candidate_id=candidate_id, currency=body.currency)
    except CandidateStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Candidate amount assessment failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Candidate amount assessment could not be completed.")


@router.get("/ledger/{transaction_id}/source")
async def get_ledger_source(transaction_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return ledger_source(db, case_id=case_id, transaction_id=transaction_id)
    except LedgerSourceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Ledger source lookup failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Ledger source could not be read.")


class AmountAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_char: int = Field(ge=0, strict=True)
    end_char: int = Field(gt=0, strict=True)
    expected_text: str = Field(min_length=1, max_length=128, strict=True)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")


@router.get("/source-files/{evidence_file_id}/text")
async def get_amount_source_text(
    evidence_file_id: UUID,
    case_id: UUID = Query(...),
    start_char: int = Query(0, ge=0),
    limit: int = Query(12000, ge=1, le=20000),
    db: Session = Depends(get_db),
):
    try:
        return read_amount_source_text(db, case_id=case_id, evidence_file_id=evidence_file_id,
                                       start_char=start_char, limit=limit)
    except AmountAssessmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Source text read failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Source text could not be read.")


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


@router.get("/candidate-sources")
async def get_candidate_sources(case_id: UUID = Query(...), limit: int = 25, offset: int = 0,
                                db: Session = Depends(get_db)):
    try:
        return list_candidate_sources(db, case_id=case_id, limit=limit, offset=offset)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    except Exception:
        logger.exception("Failed to list candidate sources")
        raise HTTPException(status_code=500, detail="Stored PDF sources could not be loaded.")


class CandidateRowSuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    date_column: int = Field(ge=0, strict=True)
    amount_column: int = Field(ge=0, strict=True)
    currency: str = Field(pattern=r"^[A-Z]{3}$", strict=True)


@router.post("/candidate-sources/{evidence_file_id}/pages/{page_number}/row-suggestions")
async def suggest_saved_source_rows(evidence_file_id: UUID, page_number: int, body: CandidateRowSuggestionRequest,
        case_id: UUID = Query(...), table_index: int = 0, db: Session = Depends(get_db)):
    from services.financial.candidate_sources import suggest_candidate_rows
    try:
        return suggest_candidate_rows(db, case_id=case_id, evidence_file_id=evidence_file_id,
            page_number=page_number, table_index=table_index, **body.model_dump())
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Stored row suggestions failed")
        raise HTTPException(status_code=500, detail="Stored row suggestions could not be prepared.")


@router.get("/candidate-sources/{evidence_file_id}/pages/{page_number}")
async def get_candidate_source(evidence_file_id: UUID, page_number: int, case_id: UUID = Query(...),
                               table_index: int = 0, db: Session = Depends(get_db)):
    try:
        return read_candidate_source(db, case_id=case_id, evidence_file_id=evidence_file_id,
                                     page_number=page_number, table_index=table_index)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    except Exception:
        logger.exception("Failed to read candidate source")
        raise HTTPException(status_code=500, detail="Stored PDF table could not be loaded.")


@router.get("/candidate-sources/{evidence_file_id}/progress")
async def get_candidate_document_progress(evidence_file_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    from services.financial.candidate_progress import candidate_document_progress
    try:
        return candidate_document_progress(db, case_id=case_id, evidence_file_id=evidence_file_id)
    except CandidateStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Failed to read document review progress")
        raise HTTPException(status_code=500, detail="Document review progress could not be loaded.")


@router.get("/candidate-sources/{evidence_file_id}/reuse-check")
async def get_candidate_source_reuse(evidence_file_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return check_candidate_source_reuse(db, case_id=case_id, evidence_file_id=evidence_file_id)
    except CandidateStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Source reuse check failed")
        raise HTTPException(status_code=500, detail="Source reuse check could not be completed.")


@router.post("/candidate-sources/{evidence_file_id}/finalization-preview")
async def preview_candidate_statement_scopes(evidence_file_id: UUID, body: StatementScopesRequest,
                                            case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return preview_candidate_finalization(db, case_id=case_id, evidence_file_id=evidence_file_id,
            resolve_path=_resolve_stored_path, statement_scopes=body.statement_scopes)
    except CandidateStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Statement scope preview failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Statement controls could not be previewed.")


@router.get("/candidate-sources/{evidence_file_id}/finalization-preview")
async def get_candidate_finalization_preview(evidence_file_id: UUID, case_id: UUID = Query(...),
                                             db: Session = Depends(get_db)):
    try:
        return preview_candidate_finalization(db, case_id=case_id,
            evidence_file_id=evidence_file_id, resolve_path=_resolve_stored_path)
    except CandidateStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception("Candidate finalization preview failed")
        raise HTTPException(status_code=500, detail="The finalization preview could not be loaded.")
    finally:
        db.rollback()


@router.get("/candidate-sources/{evidence_file_id}/statement-draft")
async def get_statement_review_draft(evidence_file_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    from services.financial.statement_review_drafts import read_statement_draft
    try:
        return read_statement_draft(db, case_id=case_id, evidence_file_id=evidence_file_id)
    except CandidateStoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


from services.financial.ledger_transfers import ledger_transfer_candidates, evaluate_transfer_scenario, LedgerTransferScenario

@router.get('/ledger-transfer-candidates')
def get_ledger_transfer_candidates(case_id: UUID = Query(...), start_date: Optional[date] = Query(None),
        end_date: Optional[date] = Query(None), population: Literal['working', 'verified'] = Query('working'),
        tolerance_days: int = Query(3, ge=0, le=7), db: Session = Depends(get_db)):
    try:
        captured = capture_ledger_export(db.get_bind(), case_id=case_id, start_date=start_date, end_date=end_date)
        return ledger_transfer_candidates(captured, population=population, tolerance_days=tolerance_days)
    except LedgerSummaryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception('Transfer candidates failed for case %s', case_id)
        raise HTTPException(status_code=500, detail='Transfer comparison could not be prepared.')


@router.post('/ledger-transfer-scenario')
def calculate_ledger_transfer_scenario(body: LedgerTransferScenario, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        captured = capture_ledger_export(db.get_bind(), case_id=case_id, start_date=body.start_date, end_date=body.end_date)
        return evaluate_transfer_scenario(captured, body)
    except LedgerSummaryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception('Transfer scenario failed for case %s', case_id)
        raise HTTPException(status_code=500, detail='Transfer scenario could not be calculated.')


@router.get('/ledger-posting-graph')
def get_ledger_posting_graph(case_id: UUID = Query(...), account_id: Optional[UUID] = Query(None),
        start_date: Optional[date] = Query(None), end_date: Optional[date] = Query(None),
        population: Literal['working', 'verified'] = Query('working'), db: Session = Depends(get_db)):
    from services.financial.ledger_graph import ledger_posting_graph
    try:
        captured = capture_ledger_export(db.get_bind(), case_id=case_id, account_id=account_id, start_date=start_date, end_date=end_date)
        return ledger_posting_graph(captured, population=population)
    except LedgerSummaryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception('Posting graph failed for case %s', case_id)
        raise HTTPException(status_code=500, detail='Posting graph could not be prepared.')
