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
    SavedAgentArtifact as SavedAgentArtifactRecord,
)
from postgres.models.user import User
from services.agent.json_utils import sanitize_text, to_jsonable, truncate_payload
from services.agent.schemas import (
    AgentArtifact,
    AgentClarification,
    AgentRunDetail,
    AgentStoredMessage,
    AgentThreadDetail,
    AgentThreadSummary,
    AgentToolTraceItem,
    SavedAgentArtifact,
)
from services.case_service import check_case_access

SUPPORTED_ARTIFACT_TYPES = {"graph", "table", "map", "report", "chart"}
SUPPORTED_SAVE_DESTINATIONS = {"workspace", "report"}


def summarize_title(message: str) -> str:
    words = sanitize_text(message).strip().split()
    title = " ".join(words[:10]) if words else "New agent thread"
    if len(title) > 80:
        title = title[:77].rstrip() + "..."
    return title or "New agent thread"


def create_thread(db: Session, *, user: User, case_id: UUID, title: str | None = None) -> AgentThread:
    thread = AgentThread(
        case_id=case_id,
        owner_user_id=user.id,
        title=sanitize_text(title or "New agent thread"),
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


def get_saved_artifact_for_user(
    db: Session,
    *,
    saved_artifact_id: UUID,
    user: User,
) -> SavedAgentArtifactRecord:
    saved = db.query(SavedAgentArtifactRecord).filter(SavedAgentArtifactRecord.id == saved_artifact_id).first()
    if not saved:
        raise ValueError("Saved artifact not found")
    check_case_access(db, saved.case_id, user, required_permission=("case", "view"))
    return saved


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
        content=sanitize_text(content),
        model_provider=sanitize_text(provider) if provider else None,
        model_id=sanitize_text(model_id) if model_id else None,
        artifact_ids=to_jsonable(artifact_ids) if artifact_ids else None,
        tool_trace_summary=to_jsonable(tool_trace_summary) if tool_trace_summary else None,
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
        provider=sanitize_text(provider),
        model_id=sanitize_text(model_id),
        input_message=sanitize_text(input_message),
        extra_metadata=to_jsonable(extra_metadata) if extra_metadata else None,
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
    run.status = sanitize_text(status)
    run.final_answer = sanitize_text(final_answer) if final_answer is not None else None
    run.error = sanitize_text(error) if error is not None else None
    run.usage = to_jsonable(usage) if usage else None
    run.completed_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(run)
    return run


def update_run_metadata(db: Session, *, run: AgentRun, metadata: dict[str, Any]) -> AgentRun:
    run.extra_metadata = to_jsonable({**(run.extra_metadata or {}), **metadata})
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
            name=sanitize_text(item.get("name") or "unknown"),
            arguments=to_jsonable(item.get("arguments") or {}),
            status=sanitize_text(item.get("status") or "error"),
            duration_ms=int(item.get("duration_ms") or 0),
            result_id=sanitize_text(item.get("result_id")) if item.get("result_id") else None,
            summary=sanitize_text(item.get("summary")) if item.get("summary") is not None else None,
            error=sanitize_text(item.get("error")) if item.get("error") is not None else None,
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
        artifact_type = sanitize_text(artifact.get("type") or "table")
        if artifact_type not in SUPPORTED_ARTIFACT_TYPES:
            continue
        artifact_id = artifact.get("id")
        record = AgentArtifactRecord(
            id=uuid.UUID(artifact_id) if artifact_id else uuid.uuid4(),
            thread_id=thread.id,
            run_id=run.id,
            type=artifact_type,
            title=sanitize_text(artifact.get("title") or "Agent artifact"),
            payload=to_jsonable(artifact.get("data") or {}),
            extra_metadata=to_jsonable(artifact.get("metadata") or {}),
        )
        db.add(record)
        records.append(record)
    db.flush()
    return records


def supported_artifacts(records: list[AgentArtifactRecord]) -> list[AgentArtifactRecord]:
    return [record for record in records if record.type in SUPPORTED_ARTIFACT_TYPES]


def to_api_artifact(record: AgentArtifactRecord) -> AgentArtifact:
    return AgentArtifact(
        id=str(record.id),
        type=record.type,
        title=record.title,
        data=record.payload or {},
        metadata=record.extra_metadata or {},
    )


def save_artifact_for_user(
    db: Session,
    *,
    artifact_id: UUID,
    user: User,
    destination: str,
    title: str,
    note: str | None = None,
) -> SavedAgentArtifactRecord:
    if destination not in SUPPORTED_SAVE_DESTINATIONS:
        raise ValueError("Unsupported save destination")
    clean_title = sanitize_text(title).strip()
    if not clean_title:
        raise ValueError("Title is required")
    clean_note = sanitize_text(note).strip()[:2000] if note else None

    artifact = get_artifact_for_user(db, artifact_id=artifact_id, user=user)
    check_case_access(db, artifact.thread.case_id, user, required_permission=("case", "edit"))

    record = SavedAgentArtifactRecord(
        case_id=artifact.thread.case_id,
        created_by_user_id=user.id,
        destination=destination,
        title=clean_title[:255],
        note=clean_note or None,
        artifact_type=artifact.type,
        artifact_payload=to_jsonable(artifact.payload or {}),
        artifact_metadata=to_jsonable(artifact.extra_metadata or {}),
        source_thread_id=artifact.thread_id,
        source_run_id=artifact.run_id,
        source_artifact_id=artifact.id,
        provenance=to_jsonable(_saved_artifact_provenance(artifact, user=user)),
    )
    db.add(record)
    db.flush()
    db.refresh(record)
    return record


def list_saved_artifacts(
    db: Session,
    *,
    user: User,
    case_id: UUID,
    destination: str | None = None,
) -> list[SavedAgentArtifact]:
    if destination is not None and destination not in SUPPORTED_SAVE_DESTINATIONS:
        raise ValueError("Unsupported save destination")
    check_case_access(db, case_id, user, required_permission=("case", "view"))
    query = db.query(SavedAgentArtifactRecord).filter(SavedAgentArtifactRecord.case_id == case_id)
    if destination:
        query = query.filter(SavedAgentArtifactRecord.destination == destination)
    rows = query.order_by(SavedAgentArtifactRecord.created_at.desc(), SavedAgentArtifactRecord.id.desc()).all()
    return [to_api_saved_artifact(row) for row in rows]


def to_api_saved_artifact(record: SavedAgentArtifactRecord) -> SavedAgentArtifact:
    return SavedAgentArtifact(
        id=str(record.id),
        case_id=str(record.case_id),
        destination=record.destination,
        title=record.title,
        note=record.note,
        artifact_type=record.artifact_type,
        artifact=AgentArtifact(
            id=str(record.id),
            type=record.artifact_type,
            title=record.title,
            data=record.artifact_payload or {},
            metadata=record.artifact_metadata or {},
        ),
        source_thread_id=str(record.source_thread_id) if record.source_thread_id else None,
        source_run_id=str(record.source_run_id) if record.source_run_id else None,
        source_artifact_id=str(record.source_artifact_id) if record.source_artifact_id else None,
        created_by_user_id=str(record.created_by_user_id) if record.created_by_user_id else None,
        provenance=record.provenance or {},
        created_at=record.created_at,
        updated_at=record.updated_at,
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


def _saved_artifact_provenance(artifact: AgentArtifactRecord, *, user: User) -> dict[str, Any]:
    run = artifact.run
    thread = artifact.thread
    return {
        "source": {
            "artifact_id": str(artifact.id),
            "artifact_type": artifact.type,
            "artifact_title": artifact.title,
            "artifact_created_at": _dt(artifact.created_at),
            "thread_id": str(thread.id) if thread else str(artifact.thread_id),
            "thread_title": thread.title if thread else None,
            "run_id": str(run.id) if run else str(artifact.run_id),
        },
        "saved_by": {
            "user_id": str(user.id),
            "email": user.email,
            "name": user.name,
        },
        "run": {
            "provider": run.provider if run else None,
            "model_id": run.model_id if run else None,
            "status": run.status if run else None,
            "started_at": _dt(run.started_at) if run else None,
            "completed_at": _dt(run.completed_at) if run else None,
            "input_message": sanitize_text(run.input_message)[:1000] if run and run.input_message else None,
            "final_answer": sanitize_text(run.final_answer)[:1000] if run and run.final_answer else None,
        },
        "artifact_metadata": artifact.extra_metadata or {},
        "tool_trace": [
            to_api_tool_trace(tool_call).model_dump(mode="json")
            for tool_call in (run.tool_calls if run else [])
        ],
    }


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


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
        artifacts=[to_api_artifact(artifact) for artifact in supported_artifacts(run.artifacts)],
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
            clarification=(
                AgentClarification(**message.run.extra_metadata["clarification"])
                if message.run
                and isinstance(message.run.extra_metadata, dict)
                and isinstance(message.run.extra_metadata.get("clarification"), dict)
                else None
            ),
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
        artifacts=[to_api_artifact(artifact) for artifact in supported_artifacts(thread.artifacts)],
    )
