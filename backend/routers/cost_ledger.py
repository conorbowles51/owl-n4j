"""
Cost Ledger Router - API endpoints for viewing OpenAI API usage and costs.
"""

from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, desc, text
from sqlalchemy.orm import Session

from postgres.session import get_db
from postgres.models.cost_record import CostRecord, CostJobType
from postgres.models.enums import GlobalRole
from postgres.models.user import User
from routers.users import get_current_db_user
from services import ai_budget

router = APIRouter(prefix="/api/cost-ledger", tags=["cost-ledger"])


def authorize_costs(db: Session, user: User, case_id: Optional[str]) -> None:
    """Who may read AI costs: an admin for any case or all cases; otherwise only someone who manages the case
    (the case.delete permission, the case owner's, the same that archives it) and only for that case.

    Before 4 Nov 2026 these routes checked only that someone was signed in: an ordinary user read all 107,338 cost
    records of every case (measured on live)."""
    if user.global_role in (GlobalRole.admin, GlobalRole.super_admin):
        return
    if not case_id:
        raise HTTPException(status_code=403, detail="Admin privileges required for costs across cases")
    from routers.case_access import authorize_case
    authorize_case(db, case_id, user, ("case", "delete"))


# --- Pydantic Schemas ---

class CostRecordResponse(BaseModel):
    id: str
    job_type: str
    provider: str
    model_id: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: float
    description: Optional[str] = None
    extra_metadata: Optional[dict] = None
    case_id: Optional[str] = None
    user_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CostLedgerResponse(BaseModel):
    records: List[CostRecordResponse]
    total: int
    total_cost: float
    total_tokens: Optional[int] = None


class CostSummaryResponse(BaseModel):
    total_cost: float
    total_tokens: Optional[int] = None
    ingestion_cost: float
    ingestion_tokens: Optional[int] = None
    ai_assistant_cost: float
    ai_assistant_tokens: Optional[int] = None
    by_model: dict[str, dict]  # {model_id: {cost, tokens, count}}


@router.get("", response_model=CostLedgerResponse)
def get_cost_ledger(
    case_id: Optional[str] = Query(None, description="Filter by case ID"),
    job_type: Optional[str] = Query(None, description="Filter by job type (ingestion, ai_assistant)"),
    model_id: Optional[str] = Query(None, description="Filter by model ID"),
    time_period: Optional[str] = Query(None, description="Filter by time period: 'day', 'week', or 'month'"),
    start_date: Optional[str] = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    """
    Get cost ledger records with optional filtering.
    """
    authorize_costs(db, user, case_id)
    query = db.query(CostRecord)
    
    # Apply filters
    if case_id:
        try:
            case_uuid = UUID(case_id)
            query = query.filter(CostRecord.case_id == case_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid case_id format")
    
    if job_type:
        if job_type not in [CostJobType.INGESTION.value, CostJobType.AI_ASSISTANT.value]:
            raise HTTPException(status_code=400, detail="Invalid job_type. Must be 'ingestion' or 'ai_assistant'")
        query = query.filter(CostRecord.job_type == job_type)
    
    if model_id:
        query = query.filter(CostRecord.model_id == model_id)
    
    # Apply time period filter (date range takes precedence over quick filters)
    if start_date or end_date:
        # Custom date range filter
        try:
            if start_date:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(CostRecord.created_at >= start_dt)
            if end_date:
                # Include the entire end date (up to 23:59:59)
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
                query = query.filter(CostRecord.created_at <= end_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    elif time_period:
        # Quick filter (only if no custom date range is set)
        now = datetime.utcnow()
        if time_period == 'day':
            start_date_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif time_period == 'week':
            # Start of current week (Monday)
            days_since_monday = now.weekday()
            start_date_dt = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif time_period == 'month':
            start_date_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            raise HTTPException(status_code=400, detail="Invalid time_period. Must be 'day', 'week', or 'month'")
        
        query = query.filter(CostRecord.created_at >= start_date_dt)
    
    # Get total count
    total = query.count()
    
    # Get records
    records = query.order_by(desc(CostRecord.created_at)).offset(offset).limit(limit).all()
    
    # Calculate totals
    total_cost_result = db.query(func.sum(CostRecord.cost_usd)).filter(
        CostRecord.id.in_([r.id for r in records])
    ).scalar() or 0.0
    
    total_tokens_result = db.query(func.sum(CostRecord.total_tokens)).filter(
        CostRecord.id.in_([r.id for r in records]),
        CostRecord.total_tokens.isnot(None)
    ).scalar()
    
    return CostLedgerResponse(
        records=[CostRecordResponse(
            id=str(r.id),
            job_type=r.job_type,
            provider=r.provider,
            model_id=r.model_id,
            prompt_tokens=r.prompt_tokens,
            completion_tokens=r.completion_tokens,
            total_tokens=r.total_tokens,
            cost_usd=float(r.cost_usd),
            description=r.description,
            extra_metadata=r.extra_metadata,
            case_id=str(r.case_id) if r.case_id else None,
            user_id=str(r.user_id) if r.user_id else None,
            created_at=r.created_at,
        ) for r in records],
        total=total,
        total_cost=float(total_cost_result),
        total_tokens=int(total_tokens_result) if total_tokens_result else None,
    )


@router.get("/summary", response_model=CostSummaryResponse)
def get_cost_summary(
    case_id: Optional[str] = Query(None, description="Filter by case ID"),
    job_type: Optional[str] = Query(None, description="Filter by job type (ingestion, ai_assistant)"),
    model_id: Optional[str] = Query(None, description="Filter by model ID"),
    time_period: Optional[str] = Query(None, description="Filter by time period: 'day', 'week', or 'month'"),
    start_date: Optional[str] = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    """
    Get cost summary statistics.
    """
    authorize_costs(db, user, case_id)
    try:
        # Helper to apply all filters to a query
        def apply_all_filters(query):
            # Case ID filter
            if case_id:
                try:
                    case_uuid = UUID(case_id)
                    query = query.filter(CostRecord.case_id == case_uuid)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid case_id format")
            
            # Job type filter
            if job_type:
                if job_type not in [CostJobType.INGESTION.value, CostJobType.AI_ASSISTANT.value]:
                    raise HTTPException(status_code=400, detail="Invalid job_type. Must be 'ingestion' or 'ai_assistant'")
                query = query.filter(CostRecord.job_type == job_type)
            
            # Model ID filter
            if model_id:
                query = query.filter(CostRecord.model_id == model_id)
            
            # Time period filter (date range takes precedence over quick filters)
            if start_date or end_date:
                try:
                    if start_date:
                        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                        query = query.filter(CostRecord.created_at >= start_dt)
                    if end_date:
                        # Include the entire end date (up to 23:59:59)
                        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                        end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
                        query = query.filter(CostRecord.created_at <= end_dt)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
            elif time_period:
                now = datetime.utcnow()
                if time_period == 'day':
                    start_date_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
                elif time_period == 'week':
                    # Start of current week (Monday)
                    days_since_monday = now.weekday()
                    start_date_dt = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
                elif time_period == 'month':
                    start_date_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                else:
                    raise HTTPException(status_code=400, detail="Invalid time_period. Must be 'day', 'week', or 'month'")
                query = query.filter(CostRecord.created_at >= start_date_dt)
            
            return query
        
        # Total cost
        total_cost_query = apply_all_filters(db.query(CostRecord))
        total_cost = total_cost_query.with_entities(func.sum(CostRecord.cost_usd)).scalar() or 0.0
        
        # Total tokens (filter out None values before aggregation)
        total_tokens_base = apply_all_filters(db.query(CostRecord))
        total_tokens = total_tokens_base.filter(CostRecord.total_tokens.isnot(None)).with_entities(
            func.sum(CostRecord.total_tokens)
        ).scalar()
        
        # Ingestion costs - use text() to bypass SQLAlchemy enum conversion
        ingestion_base = apply_all_filters(db.query(CostRecord)).filter(
            text("cost_records.job_type = 'ingestion'")
        )
        ingestion_cost = ingestion_base.with_entities(func.sum(CostRecord.cost_usd)).scalar() or 0.0
        
        ingestion_tokens_base = apply_all_filters(db.query(CostRecord)).filter(
            text("cost_records.job_type = 'ingestion'"),
            CostRecord.total_tokens.isnot(None)
        )
        ingestion_tokens = ingestion_tokens_base.with_entities(func.sum(CostRecord.total_tokens)).scalar()
        
        # AI Assistant costs - use text() to bypass SQLAlchemy enum conversion
        ai_base = apply_all_filters(db.query(CostRecord)).filter(
            text("cost_records.job_type = 'ai_assistant'")
        )
        ai_cost = ai_base.with_entities(func.sum(CostRecord.cost_usd)).scalar() or 0.0
        
        ai_tokens_base = apply_all_filters(db.query(CostRecord)).filter(
            text("cost_records.job_type = 'ai_assistant'"),
            CostRecord.total_tokens.isnot(None)
        )
        ai_tokens = ai_tokens_base.with_entities(func.sum(CostRecord.total_tokens)).scalar()
        
        # By model
        model_stats_query = apply_all_filters(
            db.query(
                CostRecord.model_id,
                func.sum(CostRecord.cost_usd).label('cost'),
                func.sum(CostRecord.total_tokens).label('tokens'),
                func.count(CostRecord.id).label('count')
            )
        )
        model_stats = model_stats_query.group_by(CostRecord.model_id).all()
        
        by_model = {}
        for model_id, cost, tokens, count in model_stats:
            by_model[model_id] = {
                "cost": float(cost or 0.0),
                "tokens": int(tokens) if tokens else None,
                "count": int(count),
            }
        
        return CostSummaryResponse(
            total_cost=float(total_cost),
            total_tokens=int(total_tokens) if total_tokens else None,
            ingestion_cost=float(ingestion_cost),
            ingestion_tokens=int(ingestion_tokens) if ingestion_tokens else None,
            ai_assistant_cost=float(ai_cost),
            ai_assistant_tokens=int(ai_tokens) if ai_tokens else None,
            by_model=by_model,
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = str(e)
        traceback_str = traceback.format_exc()
        print(f"Error in cost ledger summary: {error_detail}")
        print(f"Traceback: {traceback_str}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load cost summary: {error_detail}. Please ensure the cost_records table exists (run database migrations)."
        )


@router.get("/case-limit")
def get_case_limit(case_id: str = Query(...), user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    """The AI limit in force for one case and its spend, read-only. An administrator sets it on the AI costs page."""
    authorize_costs(db, user, case_id)
    settings = ai_budget.get_settings(db)
    return {"case_id": case_id, "limit_usd": ai_budget.case_limit(settings, case_id),
            "own_limit": case_id.lower() in settings["case_limits"],
            "spent_usd": round(ai_budget.case_spend(db, case_id), 2)}


@router.get("/case-report")
def get_case_cost_report(
    case_id: UUID = Query(..., description="The case to report"),
    start_date: Optional[str] = Query(None, description="First day, YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="Last day, YYYY-MM-DD"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    """One case's AI costs, one line per document, conversation or kind of work (FEAT-007)."""
    from services.case_cost_report import CostReportError, case_cost_report
    authorize_costs(db, user, str(case_id))
    try:
        return case_cost_report(db, case_id, start_date=start_date, end_date=end_date)
    except CostReportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/case-report.pdf")
def get_case_cost_report_pdf(
    case_id: UUID = Query(..., description="The case to report"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    """The same report as a PDF, for billing a case."""
    import re
    from services.case_cost_report import CostReportError, case_cost_report, cost_report_pdf
    authorize_costs(db, user, str(case_id))
    try:
        report = case_cost_report(db, case_id, start_date=start_date, end_date=end_date)
        content = cost_report_pdf(report)
    except CostReportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", report["case_title"] or "case").strip("-")[:80] or "case"
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="ai-costs-{name}.pdf"'})
