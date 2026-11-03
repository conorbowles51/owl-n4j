"""Phone analysis (docs/cellebrite/05 section 3). Only the decision subject is a model; the framework reads and
writes its tables with SQL (``services/phone_analysis/framework.py``)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base


class PhoneAnalysisResultSubject(Base):
    """What a confirm or reject decision is about (3.7): ``id`` is ``uuid5`` over the case, approach and
    ``result_key``, so a rerun with the same result shows the earlier decision."""

    __tablename__ = "phone_analysis_result_subjects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"),
                                               nullable=False)
    approach: Mapped[str] = mapped_column(String(40), nullable=False)
    result_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
