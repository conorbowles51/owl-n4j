"""
Cost Ledger Router - API endpoints for viewing OpenAI API usage and costs.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from postgres.session import get_db
from postgres.models.cost_record import CostRecord, CostJobType
from routers.auth import get_current_user

router = APIRouter(prefix="/api/cost-ledger", tags=["cost-ledger"])


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
async def get_cost_ledger(
    case_id: Optional[str] = Query(None, description="Filter by case ID"),
    job_type: Optional[str] = Query(None, description="Filter by job type (ingestion, ai_assistant)"),
    model_id: Optional[str] = Query(None, description="Filter by model ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Get cost ledger records with optional filtering.
    """
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
async def get_cost_summary(
    case_id: Optional[str] = Query(None, description="Filter by case ID"),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Get cost summary statistics.
    """
    # Helper to apply case_id filter to a query
    def apply_case_filter(query):
        if case_id:
            try:
                case_uuid = UUID(case_id)
                return query.filter(CostRecord.case_id == case_uuid)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid case_id format")
        return query
    
    # Total cost
    total_cost_query = apply_case_filter(db.query(CostRecord))
    total_cost = total_cost_query.with_entities(func.sum(CostRecord.cost_usd)).scalar() or 0.0
    
    # Total tokens (filter out None values before aggregation)
    total_tokens_base = apply_case_filter(db.query(CostRecord))
    total_tokens = total_tokens_base.filter(CostRecord.total_tokens.isnot(None)).with_entities(
        func.sum(CostRecord.total_tokens)
    ).scalar()
    
    # Ingestion costs
    ingestion_base = apply_case_filter(db.query(CostRecord)).filter(
        CostRecord.job_type == CostJobType.INGESTION.value
    )
    ingestion_cost = ingestion_base.with_entities(func.sum(CostRecord.cost_usd)).scalar() or 0.0
    
    ingestion_tokens_base = apply_case_filter(db.query(CostRecord)).filter(
        CostRecord.job_type == CostJobType.INGESTION.value,
        CostRecord.total_tokens.isnot(None)
    )
    ingestion_tokens = ingestion_tokens_base.with_entities(func.sum(CostRecord.total_tokens)).scalar()
    
    # AI Assistant costs
    ai_base = apply_case_filter(db.query(CostRecord)).filter(
        CostRecord.job_type == CostJobType.AI_ASSISTANT.value
    )
    ai_cost = ai_base.with_entities(func.sum(CostRecord.cost_usd)).scalar() or 0.0
    
    ai_tokens_base = apply_case_filter(db.query(CostRecord)).filter(
        CostRecord.job_type == CostJobType.AI_ASSISTANT.value,
        CostRecord.total_tokens.isnot(None)
    )
    ai_tokens = ai_tokens_base.with_entities(func.sum(CostRecord.total_tokens)).scalar()
    
    # By model
    model_stats_query = apply_case_filter(
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
