from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin

JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")


class AgentThread(Base, TimestampMixin):
    __tablename__ = "agent_threads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # RESTRICT: removing a person must never erase the run records (the disclosure record) of a live case.
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    mandate_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_mandate_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    case = relationship("Case", foreign_keys=[case_id])
    owner = relationship("User", foreign_keys=[owner_user_id])
    mandate_version = relationship("CaseMandateVersion", foreign_keys=[mandate_version_id])
    messages = relationship(
        "AgentMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="AgentMessage.sequence_number",
    )
    runs = relationship(
        "AgentRun",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="AgentRun.started_at",
    )
    artifacts = relationship(
        "AgentArtifactRecord",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="AgentArtifactRecord.created_at",
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    input_message: Mapped[str] = mapped_column(Text, nullable=False)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    mandate_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_mandate_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mandate_override: Mapped[dict | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Beaten while the run's worker lives (services.agent.run_settle); a stopped beat is a run with no worker.
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The run record (services.agent.run_record): the disclosure record of this run.
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    prompt_version_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    for_user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    for_user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tool_budget: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_calls_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unrun_tool_calls: Mapped[list | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    record_summary: Mapped[dict | None] = mapped_column(JSON_DOCUMENT, nullable=True)

    thread = relationship("AgentThread", back_populates="runs")
    case = relationship("Case", foreign_keys=[case_id])
    user = relationship("User", foreign_keys=[user_id])
    mandate_version = relationship("CaseMandateVersion", foreign_keys=[mandate_version_id])
    tool_calls = relationship(
        "AgentToolCall",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentToolCall.sequence_number",
    )
    artifacts = relationship(
        "AgentArtifactRecord",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentArtifactRecord.created_at",
    )


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (
        UniqueConstraint("thread_id", "sequence_number", name="uq_agent_messages_thread_sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    artifact_ids: Mapped[list | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    tool_trace_summary: Mapped[list | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    thread = relationship("AgentThread", back_populates="messages")
    run = relationship("AgentRun", foreign_keys=[run_id])


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence_number", name="uq_agent_tool_calls_run_sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    arguments: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_preview: Mapped[dict | list | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    # The run record, per call: what the result stated about itself and what the model was shown of it.
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    returned: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_page: Mapped[dict | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    ledger_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone_generation: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_terms: Mapped[list | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    model_paging: Mapped[list | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    model_not_shown: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_not_returned: Mapped[int | None] = mapped_column(Integer, nullable=True)
    continuation_of: Mapped[int | None] = mapped_column(Integer, nullable=True)
    record_facts: Mapped[dict | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    run = relationship("AgentRun", back_populates="tool_calls")


class AgentArtifactRecord(Base):
    __tablename__ = "agent_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    thread = relationship("AgentThread", back_populates="artifacts")
    run = relationship("AgentRun", back_populates="artifacts")


class AgentPromptVersion(Base):
    """One version of what the agent model is given: system prompt templates, answer prompts, tool schemas."""
    __tablename__ = "agent_prompt_versions"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    first_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tool_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_text: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    tool_schemas: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)


class AgentRunItem(Base):
    """One item a tool call returned, and whether the run read it further, cited it or used it (by code)."""
    __tablename__ = "agent_run_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_call_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    ref: Mapped[str] = mapped_column(String(500), nullable=False)
    label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    list_path: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shown_to_model: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    opened: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    opened_by_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    in_artifact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
