import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Enum, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    EXTRACTING_TEXT = "extracting_text"
    CHUNKING = "chunking"
    EXTRACTING_ENTITIES = "extracting_entities"
    RESOLVING_ENTITIES = "resolving_entities"
    RESOLVING_RELATIONSHIPS = "resolving_relationships"
    GENERATING_SUMMARIES = "generating_summaries"
    WRITING_GRAPH = "writing_graph"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[str] = mapped_column(String(255), index=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    file_name: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(1000))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, values_callable=lambda e: [s.value for s in e], name="jobstatus", create_type=False),
        default=JobStatus.PENDING,
    )
    progress: Mapped[float] = mapped_column(default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_count: Mapped[int] = mapped_column(default=0)
    relationship_count: Mapped[int] = mapped_column(default=0)
    llm_profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Folder context — snapshot of merged context instructions from folder chain
    folder_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sibling file awareness — JSON list of {name, mime_type, size}
    sibling_files: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
