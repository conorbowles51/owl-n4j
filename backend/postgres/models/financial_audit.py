"""Prospective financial event chain; independent of deletable source rows."""
import uuid
from sqlalchemy import BigInteger, CheckConstraint, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base


class FinancialAuditEvent(Base):
    __tablename__ = 'financial_audit_events'
    __table_args__ = (
        CheckConstraint('sequence > 0', name='ck_financial_audit_sequence'),
        CheckConstraint('length(previous_sha256)=64 AND length(entry_sha256)=64', name='ck_financial_audit_hashes'),
    )
    # No cascading case/user/source FK: deleting the subject must not erase its log.
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    previous_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Exact database-produced UTF-8 JSON text is hashed and retained, not reserialized.
    payload_text: Mapped[str] = mapped_column(Text, nullable=False)
