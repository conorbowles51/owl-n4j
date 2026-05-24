from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from postgres.models.agent import (
    AgentArtifactRecord,
    AgentMessage,
    AgentRun,
    AgentThread,
    AgentToolCall,
)
from postgres.models.user import User
from services.agent.json_utils import to_jsonable, truncate_payload
from services.agent.schemas import (
    AgentArtifact,
    AgentRunDetail,
    AgentStoredMessage,
    AgentThreadDetail,
    AgentThreadSummary,
    AgentToolTraceItem,
)
from services.case_service import check_case_access


def summarize_title(message: str) -> str:
    words = message.strip().split()
    title = " ".join(words[:10]) if words else "New agent thread"
    if len(title) > 80:
        title = title[:77].rstrip() + "..."
    return title or "New agent thread"


def create_thread(db: Session, *, user: User, case_id: UUID, title: str | None = None) -> AgentThread:
    thread = AgentThread(
        case_id=case_id,
        owner_user_id=user.id,
        title=title or "New agent thread",
        status="active",
    )
    db.add(thread)
    db.flush()
    db.refresh(thread)
    return thread


def get_thread_for_user(
    db: Session,
    *,
    thread_id: UUID,
    user: User,
    case_id: UUID | None = None,
) -> AgentThread:
    query = db.query(AgentThread).filter(AgentThread.id == thread_id)
    if case_id is not None:
        query = query.filter(AgentThread.case_id == case_id)
    thread = query.first()
    if not thread:
        raise ValueError("Agent thread not found")
    check_case_access(db, thread.case_id, user, required_permission=("case", "view"))
    if thread.owner_user_id != user.id:
        raise PermissionError("Agent thread belongs to another user")
    return thread


def get_run_for_user(db: Session, *, run_id: UUID, user: User) -> AgentRun:
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run:
        raise ValueError("Agent run not found")
    thread = get_thread_for_user(db, thread_id=run.thread_id, user=user, case_id=run.case_id)
    if thread.owner_user_id != user.id:
        raise PermissionError("Agent run belongs to another user")
    return run


def get_artifact_for_user(db: Session, *, artifact_id: UUID, user: User) -> AgentArtifactRecord:
    artifact = db.query(AgentArtifactRecord).filter(AgentArtifactRecord.id == artifact_id).first()
    if not artifact:
        raise ValueError("Agent artifact not found")
    get_thread_for_user(db, thread_id=artifact.thread_id, user=user)
    return artifact


def list_threads(db: Session, *, user: User, case_id: UUID | None = None) -> list[AgentThreadSummary]:
    query = db.query(AgentThread).filter(AgentThread.owner_user_id == user.id)
    if case_id is not None:
        check_case_access(db, case_id, user, required_permission=("case", "view"))
        query = query.filter(AgentThread.case_id == case_id)
    threads = query.order_by(AgentThread.last_message_at.desc()).limit(100).all()
    return [
        AgentThreadSummary(
            id=str(thread.id),
            case_id=str(thread.case_id),
            title=thread.title,
            status=thread.status,
            owner_user_id=str(thread.owner_user_id),
            message_count=len(thread.messages),
            last_message_at=thread.last_message_at,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
        )
        for thread in threads
    ]


def next_message_sequence(db: Session, thread_id: UUID) -> int:
    current = (
        db.query(func.max(AgentMessage.sequence_number))
        .filter(AgentMessage.thread_id == thread_id)
        .scalar()
    )
    return int(current or 0) + 1


def append_message(
    db: Session,
    *,
    thread: AgentThread,
    role: str,
    content: str,
    run: AgentRun | None = None,
    provider: str | None = None,
    model_id: str | None = None,
    artifact_ids: list[str] | None = None,
    tool_trace_summary: list[dict[str, Any]] | None = None,
) -> AgentMessage:
    message = AgentMessage(
        thread_id=thread.id,
        run_id=run.id if run else None,
        sequence_number=next_message_sequence(db, thread.id),
        role=role,
        content=content,
        model_provider=provider,
        model_id=model_id,
        artifact_ids=artifact_ids or None,
        tool_trace_summary=tool_trace_summary or None,
    )
    thread.last_message_at = datetime.now(timezone.utc)
    db.add(message)
    db.flush()
    db.refresh(message)
    return message


def recent_messages(db: Session, *, thread_id: UUID, limit: int = 20) -> list[AgentMessage]:
    rows = (
        db.query(AgentMessage)
        .filter(AgentMessage.thread_id == thread_id)
        .order_by(AgentMessage.sequence_number.desc())
        .limit(max(1, min(limit, 50)))
        .all()
    )
    return list(reversed(rows))


def create_run(
    db: Session,
    *,
    thread: AgentThread,
    user: User,
    provider: str,
    model_id: str,
    input_message: str,
    extra_metadata: dict[str, Any] | None = None,
) -> AgentRun:
    run = AgentRun(
        thread_id=thread.id,
        case_id=thread.case_id,
        user_id=user.id,
        status="running",
        provider=provider,
        model_id=model_id,
        input_message=input_message,
        extra_metadata=extra_metadata or None,
    )
    db.add(run)
    db.flush()
    db.refresh(run)
    return run


def finish_run(
    db: Session,
    *,
    run: AgentRun,
    status: str,
    final_answer: str | None = None,
    error: str | None = None,
    usage: dict[str, Any] | None = None,
) -> AgentRun:
    run.status = status
    run.final_answer = final_answer
    run.error = error
    run.usage = to_jsonable(usage) if usage else None
    run.completed_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(run)
    return run


def persist_tool_trace(
    db: Session,
    *,
    run: AgentRun,
    trace: list[dict[str, Any]],
) -> list[AgentToolCall]:
    records: list[AgentToolCall] = []
    for index, item in enumerate(trace, start=1):
        record = AgentToolCall(
            run_id=run.id,
            sequence_number=index,
            name=str(item.get("name") or "unknown"),
            arguments=to_jsonable(item.get("arguments") or {}),
            status=str(item.get("status") or "error"),
            duration_ms=int(item.get("duration_ms") or 0),
            result_id=item.get("result_id"),
            summary=item.get("summary"),
            error=item.get("error"),
            result_preview=truncate_payload(item.get("result_preview")),
        )
        db.add(record)
        records.append(record)
    db.flush()
    return records


def persist_artifacts(
    db: Session,
    *,
    thread: AgentThread,
    run: AgentRun,
    artifacts: list[dict[str, Any]],
) -> list[AgentArtifactRecord]:
    records: list[AgentArtifactRecord] = []
    for artifact in artifacts:
        artifact_id = artifact.get("id")
        record = AgentArtifactRecord(
            id=uuid.UUID(artifact_id) if artifact_id else uuid.uuid4(),
            thread_id=thread.id,
            run_id=run.id,
            type=str(artifact.get("type") or "table"),
            title=str(artifact.get("title") or "Agent artifact"),
            payload=to_jsonable(artifact.get("data") or {}),
            extra_metadata=to_jsonable(artifact.get("metadata") or {}),
        )
        db.add(record)
        records.append(record)
    db.flush()
    return records


def to_api_artifact(record: AgentArtifactRecord) -> AgentArtifact:
    return AgentArtifact(
        id=str(record.id),
        type=record.type,
        title=record.title,
        data=record.payload or {},
        metadata=record.extra_metadata or {},
    )


def to_api_tool_trace(record: AgentToolCall) -> AgentToolTraceItem:
    return AgentToolTraceItem(
        id=str(record.id),
        name=record.name,
        arguments=record.arguments or {},
        status=record.status,
        duration_ms=record.duration_ms,
        summary=record.summary,
        result_id=record.result_id,
        error=record.error,
    )


def get_run_detail(db: Session, *, run_id: UUID, user: User) -> AgentRunDetail:
    run = get_run_for_user(db, run_id=run_id, user=user)
    return AgentRunDetail(
        run_id=str(run.id),
        thread_id=str(run.thread_id),
        case_id=str(run.case_id),
        user_id=str(run.user_id) if run.user_id else None,
        status=run.status,
        provider=run.provider,
        model_id=run.model_id,
        input_message=run.input_message,
        final_answer=run.final_answer,
        error=run.error,
        usage=run.usage,
        started_at=run.started_at,
        completed_at=run.completed_at,
        artifacts=[to_api_artifact(artifact) for artifact in run.artifacts],
        tool_trace=[to_api_tool_trace(tool_call) for tool_call in run.tool_calls],
    )


def get_thread_detail(db: Session, *, thread_id: UUID, user: User) -> AgentThreadDetail:
    thread = get_thread_for_user(db, thread_id=thread_id, user=user)
    messages = [
        AgentStoredMessage(
            id=str(message.id),
            role=message.role,
            content=message.content,
            run_id=str(message.run_id) if message.run_id else None,
            model_provider=message.model_provider,
            model_id=message.model_id,
            artifact_ids=[str(item) for item in (message.artifact_ids or [])],
            tool_trace_summary=message.tool_trace_summary or [],
            created_at=message.created_at,
        )
        for message in thread.messages
    ]
    return AgentThreadDetail(
        id=str(thread.id),
        case_id=str(thread.case_id),
        title=thread.title,
        status=thread.status,
        owner_user_id=str(thread.owner_user_id),
        message_count=len(messages),
        last_message_at=thread.last_message_at,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=messages,
        artifacts=[to_api_artifact(artifact) for artifact in thread.artifacts],
    )
