"""Durable model nomination attempts; source inputs and terminal results are immutable."""
import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String, event, func, inspect
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base

class FinancialPdfNomination(Base):
    __tablename__ = 'financial_pdf_nominations'
    __table_args__ = (
        CheckConstraint("status IN ('pending','completed','failed')",name='ck_pdf_nomination_status'),
        CheckConstraint("length(request_sha256)=64",name='ck_pdf_nomination_request_hash'),
        CheckConstraint("(status='pending' AND outcome_actor IS NULL AND result IS NULL AND error_code IS NULL AND completed_at IS NULL) OR (status='completed' AND outcome_actor IS NOT NULL AND result IS NOT NULL AND error_code IS NULL AND completed_at IS NOT NULL) OR (status='failed' AND outcome_actor IS NOT NULL AND result IS NULL AND error_code IS NOT NULL AND completed_at IS NOT NULL)",name='ck_pdf_nomination_outcome'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),ForeignKey('cases.id',ondelete='CASCADE'),nullable=False,index=True)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),ForeignKey('evidence_files.id',ondelete='CASCADE'),nullable=False)
    status: Mapped[str] = mapped_column(String(16),nullable=False,default='pending')
    request_sha256: Mapped[str] = mapped_column(String(64),nullable=False)
    request: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(),'sqlite'),nullable=False)
    actor: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(),'sqlite'),nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True).with_variant(JSON(none_as_null=True),'sqlite'),nullable=True)
    outcome_actor: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True).with_variant(JSON(none_as_null=True),'sqlite'),nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64),nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)

@event.listens_for(FinancialPdfNomination,'before_update')
def _guard_nomination(mapper,connection,target):
    state=inspect(target)
    if any(state.attrs[name].history.has_changes() for name in ('id','case_id','evidence_file_id','request_sha256','request','actor','created_at')):
        raise ValueError('PDF nomination inputs are immutable.')
    previous=state.attrs.status.history.deleted
    if not previous or previous[0]!='pending' or target.status not in ('completed','failed'):
        raise ValueError('A PDF nomination can only record one terminal outcome.')

@event.listens_for(FinancialPdfNomination,'before_insert')
def _guard_initial_nomination(mapper,connection,target):
    if target.status!='pending' or target.result is not None or target.error_code is not None or target.completed_at is not None or target.outcome_actor is not None:
        raise ValueError('A model nomination must begin pending.')
    if target.request.get('case_id')!=str(target.case_id) or target.request.get('evidence_file_id')!=str(target.evidence_file_id):
        raise ValueError('Model nomination source scope is inconsistent.')
