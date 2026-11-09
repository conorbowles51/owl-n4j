from __future__ import annotations

import logging
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
from services.agent.json_utils import sanitize_text, to_jsonable, truncate_payload
from services.agent.schemas import (
    AgentArtifact,
    AgentClarification,
    AgentRunDetail,
    AgentStoredMessage,
    AgentThreadDetail,
    AgentThreadSummary,
    AgentToolTraceItem,
)
from services.case_service import check_case_access

logger = logging.getLogger(__name__)

SUPPORTED_ARTIFACT_TYPES = {"graph", "table", "map", "report", "chart"}


def summarize_title(message: str) -> str:
    words = sanitize_text(message).strip().split()
    title = " ".join(words[:10]) if words else "New agent thread"
    if len(title) > 80:
        title = title[:77].rstrip() + "..."
    return title or "New agent thread"


def create_thread(
    db: Session,
    *,
    user: User,
    case_id: UUID,
    title: str | None = None,
    mandate_version_id: UUID | None = None,
) -> AgentThread:
    thread = AgentThread(
        case_id=case_id,
        owner_user_id=user.id,
        title=sanitize_text(title or "New agent thread"),
        status="active",
        mandate_version_id=mandate_version_id,
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
            mandate_version_id=str(thread.mandate_version_id) if thread.mandate_version_id else None,
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
    mandate_override: dict[str, Any] | None = None,
    tool_budget: int | None = None,
    prompt_version: str | None = None,
    prompt_version_label: str | None = None,
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
        mandate_version_id=thread.mandate_version_id,
        mandate_override=to_jsonable(mandate_override) if mandate_override else None,
        # The person the run was for, as named when it ran (the record outlives a later change of name).
        for_user_name=sanitize_text(getattr(user, "name", None) or "")[:255] or None,
        for_user_email=sanitize_text(getattr(user, "email", None) or "")[:255] or None,
        tool_budget=tool_budget,
        prompt_version=prompt_version,
        prompt_version_label=sanitize_text(prompt_version_label)[:100] if prompt_version_label else None,
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


def checked_answer(db: Session, *, case_id, answer: str) -> tuple[str, dict[str, Any]]:
    """The answer as stored: citations in their stable form (a file named once in the case by its id, an old payment
    link as txn://), and the check of every citation against the case (services.case_citations)."""
    from services import case_citations

    try:
        with db.begin_nested():
            canonical = case_citations.canonicalize(db, case_id, answer)
            return canonical, case_citations.check_text(db, case_id, canonical)
    except Exception:  # noqa: BLE001 - an unchecked answer says so; it is never shown as checked
        logger.exception("Citation check failed for case %s", case_id)
        return answer, {"available": False, "reason": "The citations in this answer could not be checked."}


def citation_check_for(db: Session, *, case_id, content: str) -> dict[str, Any]:
    from services import case_citations

    try:
        with db.begin_nested():
            return case_citations.check_text(db, case_id, content)
    except Exception:  # noqa: BLE001
        logger.exception("Citation check failed for case %s", case_id)
        return {"available": False, "reason": "The citations in this answer could not be checked."}


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
    skip_existing: bool = False,
) -> list[AgentToolCall]:
    """Store every call of the trace. ``skip_existing``: keep the calls already stored while the run was going
    (same sequence) and store only the rest."""
    existing = {
        record.sequence_number
        for record in db.query(AgentToolCall).filter(AgentToolCall.run_id == run.id)
    } if skip_existing else set()
    records: list[AgentToolCall] = []
    for index, item in enumerate(trace, start=1):
        if index in existing:
            continue
        records.append(persist_tool_call(db, run=run, sequence=index, item=item, flush=False))
    db.flush()
    return records


def persist_tool_call(
    db: Session,
    *,
    run: AgentRun,
    sequence: int,
    item: dict[str, Any],
    flush: bool = True,
) -> AgentToolCall:
    """Store one call as soon as it has run, so a run that is stopped or dies still keeps the calls it made."""
    from services.agent.run_record import apply_facts

    record = AgentToolCall(
        run_id=run.id,
        sequence_number=sequence,
        name=sanitize_text(item.get("name") or "unknown"),
        arguments=to_jsonable(item.get("arguments") or {}),
        status=sanitize_text(item.get("status") or "error"),
        duration_ms=int(item.get("duration_ms") or 0),
        result_id=sanitize_text(item.get("result_id")) if item.get("result_id") else None,
        summary=sanitize_text(item.get("summary")) if item.get("summary") is not None else None,
        error=sanitize_text(item.get("error")) if item.get("error") is not None else None,
        result_preview=truncate_payload(item.get("result_preview")),
    )
    if isinstance(item.get("record"), dict):
        apply_facts(record, item["record"])
    db.add(record)
    if flush:
        db.flush()
    return record


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
        artifacts=[to_api_artifact(artifact) for artifact in supported_artifacts(run.artifacts)],
        tool_trace=[to_api_tool_trace(tool_call) for tool_call in run.tool_calls],
        mandate_version_id=str(run.mandate_version_id) if run.mandate_version_id else None,
        mandate_override=run.mandate_override,
        **run_progress_fields(run),
    )


def run_progress_fields(run: AgentRun) -> dict[str, Any]:
    from services.agent import live_runs
    running = run.status == "running"
    return {
        "progress": (run.extra_metadata or {}).get("progress") if running else None,
        "heartbeat_at": run.heartbeat_at,
        "stale": bool(running and live_runs.stale(run.heartbeat_at or run.started_at)),
        "server_time": datetime.now(timezone.utc),
    }


def active_runs(db: Session, *, user: User, case_id: UUID) -> list[dict[str, Any]]:
    """The person's own runs in the case still marked running, newest first (at most 5), with progress."""
    check_case_access(db, case_id, user, required_permission=("case", "view"))
    runs = (db.query(AgentRun)
            .join(AgentThread, AgentThread.id == AgentRun.thread_id)
            .filter(AgentRun.case_id == case_id, AgentRun.status == "running",
                    AgentThread.owner_user_id == user.id)
            .order_by(AgentRun.started_at.desc())
            .limit(5).all())
    out = []
    for run in runs:
        fields = run_progress_fields(run)
        out.append({
            "run_id": str(run.id),
            "thread_id": str(run.thread_id),
            "input_message": run.input_message,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "workflow": (run.extra_metadata or {}).get("workflow"),
            "progress": fields["progress"],
            "heartbeat_at": run.heartbeat_at.isoformat() if run.heartbeat_at else None,
            "stale": fields["stale"],
            "server_time": fields["server_time"].isoformat(),
        })
    return out


def _written_by(message) -> str | None:
    """The model that wrote an answer, as recorded on its run (AG-08). Runs before 9 Nov 2026 all used reasoning off."""
    if message.role != "assistant" or not message.model_id:
        return None
    meta = message.run.extra_metadata if message.run and isinstance(message.run.extra_metadata, dict) else {}
    recorded = (meta.get("model_choice") or {}).get("written_by")
    if recorded:
        return recorded
    from models.llm_models import get_model_by_id
    from services.agent.model_choice import written_by
    model = get_model_by_id(message.model_id)
    return written_by(model.name if model else message.model_id, "off")


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
            written_by=_written_by(message),
            artifact_ids=[str(item) for item in (message.artifact_ids or [])],
            tool_trace_summary=message.tool_trace_summary or [],
            citation_check=(citation_check_for(db, case_id=thread.case_id, content=message.content)
                            if message.role == "assistant" else None),
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
        mandate_version_id=str(thread.mandate_version_id) if thread.mandate_version_id else None,
        messages=messages,
        artifacts=[to_api_artifact(artifact) for artifact in supported_artifacts(thread.artifacts)],
    )
