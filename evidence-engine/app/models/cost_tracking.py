from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.job import Base


class AIPricingRate(Base):
    __tablename__ = "ai_pricing_rates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_pattern: Mapped[str] = mapped_column(String(128), nullable=False)
    operation_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    billing_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    input_cost_per_million: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    output_cost_per_million: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    duration_cost_per_minute: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    pricing_version: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CostRecord(Base):
    __tablename__ = "cost_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_type: Mapped[str] = mapped_column(
        ENUM("ingestion", "ai_assistant", name="cost_job_type", create_type=False),
        nullable=False,
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0.0)
    operation_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    engine_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # The DB-level foreign key is created by migrations in the shared schema.
    # The evidence-engine process does not map the evidence_files table locally,
    # so declaring the ORM foreign key here causes inserts to fail during SQLAlchemy
    # metadata resolution before they ever reach Postgres.
    evidence_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    pricing_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
