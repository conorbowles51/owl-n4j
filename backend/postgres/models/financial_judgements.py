"""The processor's judgement calls: a value it chose that the page does not print outright, shown to a person.

A row says which rule decided, how strongly the printed controls back it ('proved': a guess the printed controls
still prove; 'inferred': a value the page does not print), and one plain sentence a reviewer reads. A person then
confirms it or corrects it through the existing correction path (``adjudication_id`` links the correction). Nothing
is held by a judgement: it only adds information. Rows are added, never deleted; one row per subject, rule, target
and reading (re-reading the same statement records nothing new).
"""
import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base

JUDGEMENT_SUBJECTS = ('transaction', 'statement_period', 'source_document', 'account', 'evidence_file')
JUDGEMENT_STRENGTHS = ('proved', 'inferred')
JUDGEMENT_STATUSES = ('open', 'confirmed', 'corrected')
JUDGEMENT_ORIGINS = ('processor', 'agent')


def _json():
    return JSONB().with_variant(JSON(), 'sqlite')


class FinancialJudgement(Base):
    __tablename__ = 'financial_judgements'
    __table_args__ = (
        CheckConstraint(f"subject_type IN {JUDGEMENT_SUBJECTS}", name='ck_financial_judgements_subject'),
        CheckConstraint(f"strength IN {JUDGEMENT_STRENGTHS}", name='ck_financial_judgements_strength'),
        CheckConstraint(f"status IN {JUDGEMENT_STATUSES}", name='ck_financial_judgements_status'),
        CheckConstraint(f"origin IN {JUDGEMENT_ORIGINS}", name='ck_financial_judgements_origin'),
        UniqueConstraint('subject_type', 'subject_id', 'rule_id', 'target_key', 'reading',
                         name='uq_financial_judgements_reading'),
        Index('ix_financial_judgements_case', 'case_id', 'status'),
        Index('ix_financial_judgements_document', 'source_document_id'),
        Index('ix_financial_judgements_subject', 'subject_type', 'subject_id'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(24), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # The statement the subject belongs to (saved document and period), for the per-statement count and filter.
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    statement_period_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Which value of the subject (opening_balance, amount, date, currency, account, copy, ...); '' = the subject.
    target_key: Mapped[str] = mapped_column(String(48), nullable=False, default='')
    # What was read (the saved document, or the reading revision): the same reading never records twice.
    reading: Mapped[str] = mapped_column(String(80), nullable=False, default='')
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default='processor')
    strength: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(_json(), nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='open')
    resolved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    adjudication_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
