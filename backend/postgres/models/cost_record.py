from __future__ import annotations

import uuid
from enum import Enum
from sqlalchemy import String, ForeignKey, Integer, Numeric, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


class CostJobType(str, Enum):
    """Type of job that incurred the cost."""
    INGESTION = "ingestion"
    AI_ASSISTANT = "ai_assistant"


class CostRecord(Base, TimestampMixin):
    """Records OpenAI API usage and costs."""
    __tablename__ = "cost_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Job information
    job_type: Mapped[str] = mapped_column(
        SQLEnum(CostJobType, name="cost_job_type"),
        nullable=False,
        index=True,
    )
    
    # Optional case association
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    # Optional user association
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Model information
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # "openai" or "ollama"
    model_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # Token usage (only for OpenAI)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Cost calculation (in USD)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0.0)
    
    # Additional metadata
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Brief description of the job
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # Additional context (question, document name, etc.)

    # Relationships
    case = relationship("Case", foreign_keys=[case_id])
    user = relationship("User", foreign_keys=[user_id])
