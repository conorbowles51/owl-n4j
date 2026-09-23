"""Private file transfers; no evidence row until finalisation."""
import uuid
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base


class EvidenceUploadGroup(Base):
    """A retained folder/archive selection and its one-time registration receipt."""
    __tablename__ = 'evidence_upload_groups'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('evidence_folders.id', ondelete='CASCADE'), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20))
    replace_existing: Mapped[bool] = mapped_column(Boolean, default=False)
    manifest: Mapped[list] = mapped_column(JSONB().with_variant(JSON(), 'sqlite'))
    receipt: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSON(), 'sqlite'), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='uploading')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EvidenceUploadSession(Base):
    __tablename__ = 'evidence_upload_sessions'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('evidence_folders.id', ondelete='CASCADE'), nullable=True)
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('evidence_upload_groups.id', ondelete='CASCADE'), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(1024))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    chunk_size: Mapped[int] = mapped_column(Integer)
    chunks: Mapped[list] = mapped_column(JSONB().with_variant(JSON(), 'sqlite'))
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('evidence_files.id', ondelete='SET NULL'), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='uploading')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
