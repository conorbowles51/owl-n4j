from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


class ProcessingProfile(Base, TimestampMixin):
    __tablename__ = "processing_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    mandatory_instructions: Mapped[list] = mapped_column(JSONB, server_default="[]", nullable=False)
    special_entity_types: Mapped[list] = mapped_column(JSONB, server_default="[]", nullable=False)


class CaseProcessingConfig(Base, TimestampMixin):
    __tablename__ = "case_processing_configs"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processing_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_profile_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    context_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    mandatory_instructions: Mapped[list] = mapped_column(JSONB, server_default="[]", nullable=False)
    special_entity_types: Mapped[list] = mapped_column(JSONB, server_default="[]", nullable=False)

    case = relationship("Case", foreign_keys=[case_id])
    source_profile = relationship("ProcessingProfile", foreign_keys=[source_profile_id])
