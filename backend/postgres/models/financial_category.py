"""Reusable category names, independent of any case's payment records."""
from datetime import datetime
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base


class FinancialCategory(Base):
    __tablename__ = 'financial_categories'
    normalized_name: Mapped[str] = mapped_column(String(360), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
