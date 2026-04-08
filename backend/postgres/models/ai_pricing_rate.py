from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


class AIPricingRate(Base, TimestampMixin):
    __tablename__ = "ai_pricing_rates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model_pattern: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    operation_kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    billing_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    input_cost_per_million: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    output_cost_per_million: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    duration_cost_per_minute: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    pricing_version: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
