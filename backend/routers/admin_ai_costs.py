from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case as sql_case, func
from sqlalchemy.orm import Session

from postgres.models.case import Case
from postgres.models.cost_record import CostRecord
from postgres.models.evidence import EvidenceFile
from postgres.models.user import User
from postgres.session import get_db
from routers.users import require_admin


router = APIRouter(prefix="/api/admin/ai-costs", tags=["admin-ai-costs"])


SourceParam = Literal["ingestion", "chat"]


class SelectOption(BaseModel):
    value: str
    label: str


class UserOption(BaseModel):
    id: str
    name: str
    email: str


class CaseOption(BaseModel):
    id: str
    title: str


class AICostFiltersResponse(BaseModel):
    users: list[UserOption]
    cases: list[CaseOption]


class SummaryBreakdownItem(BaseModel):
    key: str
    label: str
    cost_usd: float
    request_count: int


class AICostSummaryResponse(BaseModel):
    total_cost_usd: float
    ingestion_cost_usd: float
    chat_cost_usd: float
    billable_calls: int
    top_models: list[SummaryBreakdownItem]
    top_users: list[SummaryBreakdownItem]


class TimeseriesPoint(BaseModel):
    bucket_date: str
    ingestion_cost_usd: float
    chat_cost_usd: float
    total_cost_usd: float


class AICostTimeseriesResponse(BaseModel):
    points: list[TimeseriesPoint]


class AICostRecord(BaseModel):
    id: str
    created_at: str
    source: str
    operation_kind: str | None = None
    provider: str
    model_id: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float
    pricing_version: str | None = None
    description: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    user_email: str | None = None
    case_id: str | None = None
    case_title: str | None = None
    engine_job_id: str | None = None
    evidence_file_id: str | None = None
    evidence_file_name: str | None = None
    conversation_id: str | None = None
    extra_metadata: dict | None = None


class AICostRecordsResponse(BaseModel):
    records: list[AICostRecord]
    total_count: int
    total_cost_usd: float
    page: int
    page_size: int


def _parse_datetime(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD") from exc
    if end_of_day:
        parsed = parsed + timedelta(days=1) - timedelta(microseconds=1)
    return parsed


def _apply_filters(
    query,
    *,
    source: str | None,
    user_id: str | None,
    case_id: str | None,
    provider: str | None,
    model_id: str | None,
    operation_kind: str | None,
    start_date: str | None,
    end_date: str | None,
):
    if source:
        source_map = {
            "ingestion": "ingestion",
            "chat": "ai_assistant",
        }
        mapped_source = source_map.get(source)
        if mapped_source is None:
            raise HTTPException(status_code=400, detail="Invalid source filter")
        query = query.filter(CostRecord.job_type == mapped_source)

    if user_id:
        try:
            query = query.filter(CostRecord.user_id == UUID(user_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid user_id filter") from exc

    if case_id:
        try:
            query = query.filter(CostRecord.case_id == UUID(case_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid case_id filter") from exc

    if provider:
        query = query.filter(CostRecord.provider == provider)
    if model_id:
        query = query.filter(CostRecord.model_id == model_id)
    if operation_kind:
        query = query.filter(CostRecord.operation_kind == operation_kind)

    start_dt = _parse_datetime(start_date)
    end_dt = _parse_datetime(end_date, end_of_day=True)
    if start_dt:
        query = query.filter(CostRecord.created_at >= start_dt)
    if end_dt:
        query = query.filter(CostRecord.created_at <= end_dt)
    return query


@router.get("/filters", response_model=AICostFiltersResponse)
def get_ai_cost_filters(
    source: SourceParam | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    users = (
        db.query(User.id.label("id"), User.name.label("name"), User.email.label("email"))
        .filter(User.is_active.is_(True))
        .order_by(User.name.asc(), User.email.asc())
        .all()
    )
    cases = (
        db.query(Case.id.label("id"), Case.title.label("title"))
        .order_by(Case.title.asc())
        .all()
    )

    return AICostFiltersResponse(
        users=[
            UserOption(id=str(user.id), name=user.name, email=user.email)
            for user in users
        ],
        cases=[
            CaseOption(id=str(case.id), title=case.title)
            for case in cases
        ],
    )


@router.get("/summary", response_model=AICostSummaryResponse)
def get_ai_cost_summary(
    source: SourceParam | None = Query(None),
    user_id: str | None = Query(None),
    case_id: str | None = Query(None),
    provider: str | None = Query(None),
    model_id: str | None = Query(None),
    operation_kind: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    base = _apply_filters(
        db.query(CostRecord),
        source=source,
        user_id=user_id,
        case_id=case_id,
        provider=provider,
        model_id=model_id,
        operation_kind=operation_kind,
        start_date=start_date,
        end_date=end_date,
    )

    total_cost_usd = float(
        base.with_entities(func.coalesce(func.sum(CostRecord.cost_usd), 0)).scalar() or 0
    )
    ingestion_cost_usd = float(
        base.filter(CostRecord.job_type == "ingestion")
        .with_entities(func.coalesce(func.sum(CostRecord.cost_usd), 0))
        .scalar()
        or 0
    )
    chat_cost_usd = float(
        base.filter(CostRecord.job_type == "ai_assistant")
        .with_entities(func.coalesce(func.sum(CostRecord.cost_usd), 0))
        .scalar()
        or 0
    )
    billable_calls = int(
        base.filter(CostRecord.cost_usd > 0)
        .with_entities(func.count(CostRecord.id))
        .scalar()
        or 0
    )

    top_models = (
        base.with_entities(
            CostRecord.model_id,
            func.coalesce(func.sum(CostRecord.cost_usd), 0).label("cost_usd"),
            func.count(CostRecord.id).label("request_count"),
        )
        .group_by(CostRecord.model_id)
        .order_by(func.sum(CostRecord.cost_usd).desc(), CostRecord.model_id.asc())
        .limit(5)
        .all()
    )
    top_users = (
        base.outerjoin(User, CostRecord.user_id == User.id)
        .with_entities(
            CostRecord.user_id,
            User.name,
            User.email,
            func.coalesce(func.sum(CostRecord.cost_usd), 0).label("cost_usd"),
            func.count(CostRecord.id).label("request_count"),
        )
        .group_by(CostRecord.user_id, User.name, User.email)
        .order_by(func.sum(CostRecord.cost_usd).desc(), User.name.asc(), User.email.asc())
        .limit(5)
        .all()
    )

    return AICostSummaryResponse(
        total_cost_usd=total_cost_usd,
        ingestion_cost_usd=ingestion_cost_usd,
        chat_cost_usd=chat_cost_usd,
        billable_calls=billable_calls,
        top_models=[
            SummaryBreakdownItem(
                key=item.model_id,
                label=item.model_id,
                cost_usd=float(item.cost_usd or 0),
                request_count=int(item.request_count or 0),
            )
            for item in top_models
        ],
        top_users=[
            SummaryBreakdownItem(
                key=str(item.user_id) if item.user_id else "unknown",
                label=item.name or item.email or "Unknown/System",
                cost_usd=float(item.cost_usd or 0),
                request_count=int(item.request_count or 0),
            )
            for item in top_users
        ],
    )


@router.get("/timeseries", response_model=AICostTimeseriesResponse)
def get_ai_cost_timeseries(
    source: SourceParam | None = Query(None),
    user_id: str | None = Query(None),
    case_id: str | None = Query(None),
    provider: str | None = Query(None),
    model_id: str | None = Query(None),
    operation_kind: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    base = _apply_filters(
        db.query(CostRecord),
        source=source,
        user_id=user_id,
        case_id=case_id,
        provider=provider,
        model_id=model_id,
        operation_kind=operation_kind,
        start_date=start_date,
        end_date=end_date,
    )

    day_bucket = func.date_trunc("day", CostRecord.created_at)
    rows = (
        base.with_entities(
            day_bucket.label("bucket_date"),
            func.coalesce(
                func.sum(
                    sql_case((CostRecord.job_type == "ingestion", CostRecord.cost_usd), else_=0)
                ),
                0,
            ).label("ingestion_cost_usd"),
            func.coalesce(
                func.sum(
                    sql_case((CostRecord.job_type == "ai_assistant", CostRecord.cost_usd), else_=0)
                ),
                0,
            ).label("chat_cost_usd"),
            func.coalesce(func.sum(CostRecord.cost_usd), 0).label("total_cost_usd"),
        )
        .group_by(day_bucket)
        .order_by(day_bucket.asc())
        .all()
    )

    return AICostTimeseriesResponse(
        points=[
            TimeseriesPoint(
                bucket_date=row.bucket_date.date().isoformat(),
                ingestion_cost_usd=float(row.ingestion_cost_usd or 0),
                chat_cost_usd=float(row.chat_cost_usd or 0),
                total_cost_usd=float(row.total_cost_usd or 0),
            )
            for row in rows
        ]
    )


@router.get("/records", response_model=AICostRecordsResponse)
def get_ai_cost_records(
    source: SourceParam | None = Query(None),
    user_id: str | None = Query(None),
    case_id: str | None = Query(None),
    provider: str | None = Query(None),
    model_id: str | None = Query(None),
    operation_kind: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    base = _apply_filters(
        db.query(CostRecord),
        source=source,
        user_id=user_id,
        case_id=case_id,
        provider=provider,
        model_id=model_id,
        operation_kind=operation_kind,
        start_date=start_date,
        end_date=end_date,
    )

    total_count = int(base.with_entities(func.count(CostRecord.id)).scalar() or 0)
    total_cost_usd = float(
        base.with_entities(func.coalesce(func.sum(CostRecord.cost_usd), 0)).scalar() or 0
    )

    rows = (
        base.outerjoin(User, CostRecord.user_id == User.id)
        .outerjoin(Case, CostRecord.case_id == Case.id)
        .outerjoin(EvidenceFile, CostRecord.evidence_file_id == EvidenceFile.id)
        .with_entities(
            CostRecord,
            User.name.label("user_name"),
            User.email.label("user_email"),
            Case.title.label("case_title"),
            EvidenceFile.original_filename.label("evidence_file_name"),
        )
        .order_by(CostRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    records = []
    for row in rows:
        record = row[0]
        metadata = record.extra_metadata or {}
        records.append(
            AICostRecord(
                id=str(record.id),
                created_at=record.created_at.isoformat() if record.created_at else "",
                source="Ingestion" if record.job_type == "ingestion" else "Chat",
                operation_kind=record.operation_kind,
                provider=record.provider,
                model_id=record.model_id,
                prompt_tokens=record.prompt_tokens,
                completion_tokens=record.completion_tokens,
                total_tokens=record.total_tokens,
                cost_usd=float(record.cost_usd or 0),
                pricing_version=record.pricing_version,
                description=record.description,
                user_id=str(record.user_id) if record.user_id else None,
                user_name=row.user_name,
                user_email=row.user_email,
                case_id=str(record.case_id) if record.case_id else None,
                case_title=row.case_title,
                engine_job_id=record.engine_job_id,
                evidence_file_id=str(record.evidence_file_id) if record.evidence_file_id else None,
                evidence_file_name=row.evidence_file_name,
                conversation_id=metadata.get("conversation_id"),
                extra_metadata=metadata or None,
            )
        )

    return AICostRecordsResponse(
        records=records,
        total_count=total_count,
        total_cost_usd=total_cost_usd,
        page=page,
        page_size=page_size,
    )
