"""Each payment's category, stored: what it is, who or what set it, and on what basis.

One row per ledger transaction. ``origin`` says who decided: 'person' (an investigator chose it), 'rule' (the
description rules in payment_inference), 'model' (the model classifier, for what the rules cannot place) or
'learned' (a person applied their choice to the payments like it). A person's choice is never replaced by any
automatic pass. The category text is the same name the ledger, filters, exports and charts show; '' means a person
marked the payment Uncategorized.

``financial_category_model_cache`` keeps the model's answer per description stem, across cases, so a description
already classified is not sent again.
"""
import uuid
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base

CATEGORY_ORIGINS = ('person', 'rule', 'model', 'learned')


class FinancialPaymentCategory(Base):
    __tablename__ = 'financial_payment_categories'
    __table_args__ = (
        CheckConstraint(f"origin IN {CATEGORY_ORIGINS}", name='ck_financial_payment_categories_origin'),
        Index('ix_financial_payment_categories_case_category', 'case_id', 'category'),
        Index('ix_financial_payment_categories_case_stem', 'case_id', 'stem'),
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('financial_transactions.id', ondelete='CASCADE'), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'),
                                               nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False, default='')
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    # The rule id, the model id, or the payment a learned choice came from.
    basis: Mapped[str] = mapped_column(String(160), nullable=False, default='')
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    why: Mapped[str | None] = mapped_column(Text, nullable=True)
    stem: Mapped[str] = mapped_column(String(200), nullable=False, default='')
    set_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(),
                                             default=func.now())


class FinancialCategoryModelCache(Base):
    __tablename__ = 'financial_category_model_cache'
    stem: Mapped[str] = mapped_column(String(200), primary_key=True)
    direction: Mapped[str] = mapped_column(String(8), primary_key=True)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    why: Mapped[str] = mapped_column(Text, nullable=False, default='')
    model: Mapped[str] = mapped_column(String(120), nullable=False, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(),
                                                 default=func.now())


class FinancialCategoryRule(Base):
    """A person's rule: payments in this case described like ``match_value`` (its description stem) or with this
    printed counterparty get ``category``, as 'learned', when they are saved. A person's own choice on a payment still
    wins. Retiring a rule keeps it (``active`` False) and leaves the payments it placed as they are."""
    __tablename__ = 'financial_category_rules'
    __table_args__ = (
        CheckConstraint("match_kind IN ('description', 'counterparty')", name='ck_financial_category_rules_kind'),
        Index('ix_financial_category_rules_case_match', 'case_id', 'match_kind', 'match_value', unique=True),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'),
                                               nullable=False)
    match_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    match_value: Mapped[str] = mapped_column(String(200), nullable=False)
    # What the person saw when they made it: the description or counterparty as printed.
    example: Mapped[str] = mapped_column(Text, nullable=False, default='')
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    from_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(),
                                                 default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(),
                                                 default=func.now())
