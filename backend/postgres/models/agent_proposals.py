"""What a person did with the case agent's proposals, and the proceeds calculations whose assumptions are calls.

``AgentProposalSourceOpen``: one cited source a person opened from a proposal (a judgement call the agent proposed,
or a drafted Workspace AI output). A confirmation reads these to record whether its source was opened first; the
screen enables its confirm button only after one was. Rows are added, never changed.

``ProceedsCalculation``: a proceeds calculation (scenario 8). Its assumptions are judgement calls on subject
``calculation``; the result is computed from them on every read and is never stored.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base

PROPOSAL_TYPES = ('judgement', 'workspace_ai')


class AgentProposalSourceOpen(Base):
    __tablename__ = 'agent_proposal_source_opens'
    __table_args__ = (
        CheckConstraint("proposal_type IN ('judgement', 'workspace_ai')", name='ck_agent_proposal_opens_type'),
        Index('ix_agent_proposal_opens_proposal', 'proposal_type', 'proposal_id', 'user_id'),
        Index('ix_agent_proposal_opens_case', 'case_id', 'opened_at'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'),
                                               nullable=False)
    proposal_type: Mapped[str] = mapped_column(String(24), nullable=False)
    proposal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    citation: Mapped[str] = mapped_column(String(600), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'),
                                                      nullable=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProceedsCalculation(Base):
    __tablename__ = 'proceeds_calculations'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'),
                                               nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(),
                                                 onupdate=func.now())
