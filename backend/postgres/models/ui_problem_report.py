"""Report a problem on a phone screen (07 section 9): structured fields, optional free text, no screenshot.

Case access rules apply: a report belongs to its case, and only people with access to that case, and admins,
can read it. The free text stays in this table; the team is told only ids, kinds, counts and the build id
(services.ui_problem_reports.jobs_line).
"""
import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base


class UiProblemReport(Base):
    __tablename__ = 'ui_problem_reports'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    screen: Mapped[str] = mapped_column(String(64), nullable=False)
    action_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # "yes", "no" or "not-tried": whether refreshing the page changes it.
    refresh_changes: Mapped[str] = mapped_column(String(16), nullable=False)
    build_id: Mapped[str] = mapped_column(String(64), nullable=False)
    last_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    viewport_w: Mapped[int | None] = mapped_column(Integer, nullable=True)
    viewport_h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Kinds and counts only, e.g. {"messages": 2140, "phones": 3}.
    scope: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), 'sqlite'), nullable=False, default=dict)
    # Component ids of the area, e.g. ["phone-table", "record-panel"].
    components: Mapped[list] = mapped_column(JSONB().with_variant(JSON(), 'sqlite'), nullable=False, default=list)
    # "What did you expect?": optional, kept in the database only, never sent to jobs.
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
