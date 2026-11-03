"""Machine generations, immutable investigator revisions and review receipts."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base
from postgres.models.evidence import _jsonb_column
from sqlalchemy import Uuid


class TranscriptSource(Base):
    __tablename__ = 'evidence_transcription_sources'
    __table_args__ = (
        UniqueConstraint('id', 'evidence_file_id', 'case_id', name='uq_audio_source_scope'),
        ForeignKeyConstraint(['evidence_file_id', 'case_id'], ['evidence_files.id', 'evidence_files.case_id'], ondelete='CASCADE', name='fk_audio_source_case'),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('evidence_files.id', ondelete='CASCADE'), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    engine_job_id: Mapped[str] = mapped_column(String(64), unique=True)
    source_sha256: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    segments: Mapped[list] = mapped_column(_jsonb_column())
    metadata_: Mapped[dict] = mapped_column('metadata', _jsonb_column(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TranscriptRevision(Base):
    __tablename__ = 'evidence_transcript_revisions'
    __table_args__ = (
        UniqueConstraint('id', 'evidence_file_id', 'case_id', name='uq_audio_revision_scope'),
        ForeignKeyConstraint(['source_id', 'evidence_file_id', 'case_id'], ['evidence_transcription_sources.id', 'evidence_transcription_sources.evidence_file_id', 'evidence_transcription_sources.case_id'], name='fk_audio_revision_source'),
        ForeignKeyConstraint(['parent_id', 'evidence_file_id', 'case_id'], ['evidence_transcript_revisions.id', 'evidence_transcript_revisions.evidence_file_id', 'evidence_transcript_revisions.case_id'], name='fk_audio_revision_parent'),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('evidence_files.id', ondelete='CASCADE'), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('evidence_transcription_sources.id'))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    payload: Mapped[dict] = mapped_column(_jsonb_column())
    digest: Mapped[str] = mapped_column(String(64))
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TranscriptState(Base):
    __tablename__ = 'evidence_transcript_state'
    __table_args__ = (
        ForeignKeyConstraint(['source_id', 'evidence_file_id', 'case_id'], ['evidence_transcription_sources.id', 'evidence_transcription_sources.evidence_file_id', 'evidence_transcription_sources.case_id'], name='fk_audio_state_source'),
        *(ForeignKeyConstraint([field, 'evidence_file_id', 'case_id'], ['evidence_transcript_revisions.id', 'evidence_transcript_revisions.evidence_file_id', 'evidence_transcript_revisions.case_id'], name=f'fk_audio_state_{field}')
          for field in ('working_revision_id', 'reviewed_revision_id', 'published_revision_id')),
    )
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('evidence_files.id', ondelete='CASCADE'), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    working_revision_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    reviewed_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    published_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    review_required: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


class TranscriptReview(Base):
    __tablename__ = 'evidence_transcript_reviews'
    __table_args__ = (UniqueConstraint('evidence_file_id', 'request_key'),
        ForeignKeyConstraint(['revision_id', 'evidence_file_id', 'case_id'], ['evidence_transcript_revisions.id', 'evidence_transcript_revisions.evidence_file_id', 'evidence_transcript_revisions.case_id'], name='fk_audio_review_revision'))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('evidence_files.id', ondelete='CASCADE'), index=True)
    revision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('evidence_transcript_revisions.id'))
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    request_key: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceProcessingPlan(Base):
    __tablename__ = 'evidence_processing_plans'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('cases.id', ondelete='CASCADE'), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    payload: Mapped[dict] = mapped_column(_jsonb_column())
    execution: Mapped[dict | None] = mapped_column(_jsonb_column(), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
