from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


AgentArtifactType = Literal["graph", "table", "map", "report", "chart"]
AgentToolStatus = Literal["success", "error"]
AgentRunStatus = Literal["running", "completed", "failed", "cancelled", "clarification_required"]
AgentArtifactPreference = Literal[
    "auto",
    "none",
    "graph",
    "table",
    "map",
    "report",
    "chart",
]


class AgentMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=12000)
    case_id: UUID
    thread_id: UUID | None = None
    provider: str = "openai"
    model: str = "gpt-5-mini"
    artifact_preference: AgentArtifactPreference = "auto"
    case_layer: Literal["all", "significant"] = "all"
    persist: bool = True

    @field_validator("message")
    @classmethod
    def _message_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Message is required")
        return stripped

    @field_validator("provider")
    @classmethod
    def _normalize_provider(cls, value: str) -> str:
        return value.lower().strip()


class AgentModelInfo(BaseModel):
    provider: str
    model_id: str
    model_name: str
    server: str


class AgentCost(BaseModel):
    usd: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_record_id: str | None = None


class AgentArtifact(BaseModel):
    id: str
    type: AgentArtifactType
    title: str
    data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentToolTraceItem(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: AgentToolStatus
    duration_ms: int
    summary: str | None = None
    result_id: str | None = None
    error: str | None = None
    activity: dict[str, Any] | None = None


class AgentClarificationOption(BaseModel):
    id: str
    label: str
    description: str | None = None


class AgentClarification(BaseModel):
    question: str
    options: list[AgentClarificationOption] = Field(default_factory=list)
    allow_free_text: bool = True
    pending_run_id: str
    thread_id: str
    original_message: str
    context: dict[str, Any] = Field(default_factory=dict)


class AgentMessageResponse(BaseModel):
    thread_id: str
    run_id: str
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    answer: str
    artifacts: list[AgentArtifact] = Field(default_factory=list)
    tool_trace: list[AgentToolTraceItem] = Field(default_factory=list)
    model_info: AgentModelInfo
    cost: AgentCost | None = None
    clarification: AgentClarification | None = None
    status: AgentRunStatus
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AgentRunStatusResponse(BaseModel):
    run_id: str
    thread_id: str
    status: AgentRunStatus
    error: str | None = None
    completed_at: datetime | None = None


class AgentRunDetail(AgentRunStatusResponse):
    case_id: str
    user_id: str | None = None
    provider: str
    model_id: str
    input_message: str
    final_answer: str | None = None
    usage: dict[str, Any] | None = None
    started_at: datetime
    artifacts: list[AgentArtifact] = Field(default_factory=list)
    tool_trace: list[AgentToolTraceItem] = Field(default_factory=list)


class AgentThreadSummary(BaseModel):
    id: str
    case_id: str
    title: str
    status: str
    owner_user_id: str
    message_count: int
    last_message_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentStoredMessage(BaseModel):
    id: str
    role: str
    content: str
    run_id: str | None = None
    model_provider: str | None = None
    model_id: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    tool_trace_summary: list[dict[str, Any]] = Field(default_factory=list)
    clarification: AgentClarification | None = None
    created_at: datetime


class AgentThreadDetail(AgentThreadSummary):
    messages: list[AgentStoredMessage] = Field(default_factory=list)
    artifacts: list[AgentArtifact] = Field(default_factory=list)
