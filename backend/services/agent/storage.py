from __future__ import annotations

import logging
import uuid
import copy
import json
from collections import OrderedDict
from threading import RLock
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

from services.agent.deliverables import ARTIFACT_TYPES

SUPPORTED_ARTIFACT_TYPES = ARTIFACT_TYPES


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
    check_run_source_access(db, run, user)
    return run


def check_run_source_access(db, run, user):
    from services.agent.all_cases import may_open
    meta = run.extra_metadata or {}
    source_ids = {str(c['case_id']) for c in meta.get('cases_read', []) if isinstance(c, dict) and c.get('case_id')}
    source_ids.update((meta.get('execution_checkpoint') or {}).get('cases_read', {}).keys())
    for source_id in source_ids:
        if source_id != str(run.case_id) and not may_open(db, user, source_id):
            raise PermissionError("Access to a source case changed; this saved answer cannot be opened.")


def readable_artifacts(db, artifacts, user):
    readable = []
    for artifact in supported_artifacts(artifacts):
        try:
            check_artifact_access(db, artifact, user)
        except PermissionError:
            continue
        readable.append(artifact)
    return readable


def get_artifact_for_user(db: Session, *, artifact_id: UUID, user: User) -> AgentArtifactRecord:
    artifact = db.query(AgentArtifactRecord).filter(AgentArtifactRecord.id == artifact_id).first()
    if not artifact:
        raise ValueError("Agent artifact not found")
    get_thread_for_user(db, thread_id=artifact.thread_id, user=user)
    check_artifact_access(db, artifact, user)
    return artifact


def check_artifact_access(db, artifact, user):
    """Saved cross-case outputs retain their source access requirements after export or reopen."""
    from services.agent.all_cases import may_open
    meta = artifact.extra_metadata or {}
    run_meta = artifact.run.extra_metadata or {} if artifact.run else {}
    source_ids = set(meta.get("source_case_ids") or [])
    source_ids.update(str(c["case_id"]) for c in run_meta.get("cases_read", []) if isinstance(c, dict) and c.get("case_id"))
    source_ids.update((run_meta.get("execution_checkpoint") or {}).get("cases_read", {}).keys())
    own_case = str(artifact.thread.case_id)
    if (meta.get("all_cases") or run_meta.get("all_cases")) and not source_ids:
        raise PermissionError("This older cross-case artifact has no source-access record; rebuild it before opening.")
    for source_id in source_ids:
        if source_id != own_case and not may_open(db, user, source_id):
            raise PermissionError("Access to a source case changed; this artifact cannot be opened.")


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
    from services.agent.durable_execution import write_metadata
    write_metadata(db, run, metadata)
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
    # All revision writers serialize on the thread, including the interactive edit API.
    db.query(AgentThread).filter(AgentThread.id == thread.id).with_for_update().first()
    records: list[AgentArtifactRecord] = []
    for artifact in artifacts:
        artifact_type = sanitize_text(artifact.get("type") or "table")
        if artifact_type not in SUPPORTED_ARTIFACT_TYPES:
            continue
        artifact_id = artifact.get("id")
        if artifact_id:
            existing = db.get(AgentArtifactRecord, uuid.UUID(str(artifact_id)))
            if existing is not None:
                if existing.thread_id != thread.id:
                    raise PermissionError("Artifact belongs to another conversation")
                records.append(existing)
                continue
        metadata = dict(artifact.get("metadata") or {})
        previous_id = metadata.get("previous_revision_id")
        if previous_id:
            previous = db.get(AgentArtifactRecord, uuid.UUID(str(previous_id)))
            if previous is None or previous.thread_id != thread.id:
                raise ValueError("The report revision is not in this conversation")
            deliverable_id = metadata.get("deliverable_id")
            siblings = db.query(AgentArtifactRecord).filter(AgentArtifactRecord.thread_id == thread.id).all()
            current = max((a for a in siblings if (a.extra_metadata or {}).get("deliverable_id", str(a.id)) == deliverable_id),
                          key=lambda a: int((a.extra_metadata or {}).get("revision", 1)), default=previous)
            if current.id != previous.id:
                # Keep generated work as a separate conflict draft; never replace the investigator's newer revision.
                metadata.update(conflict_draft=True, intended_deliverable_id=deliverable_id,
                                deliverable_id=artifact_id, revision=1)
                metadata.pop("previous_revision_id", None)
                metadata["validation"] = {"status": "needs_revision", "issues": [
                    "The source report changed while this revision was prepared. Review and merge this draft."]}
        record = AgentArtifactRecord(
            id=uuid.UUID(artifact_id) if artifact_id else uuid.uuid4(),
            thread_id=thread.id,
            run_id=run.id,
            type=artifact_type,
            title=sanitize_text(artifact.get("title") or "Agent artifact"),
            payload=to_jsonable(artifact.get("data") or {}),
            extra_metadata=to_jsonable(metadata),
        )
        db.add(record)
        records.append(record)
    db.flush()
    return records


def supported_artifacts(records: list[AgentArtifactRecord]) -> list[AgentArtifactRecord]:
    return [record for record in records if record.type in SUPPORTED_ARTIFACT_TYPES]


def to_api_artifact(record: AgentArtifactRecord) -> AgentArtifact:
    metadata = copy.deepcopy(record.extra_metadata or {})
    metadata.pop('completion_review', None)
    run = getattr(record, 'run', None)
    run_metadata = (run.extra_metadata or {}) if run else {}
    completed = run_metadata.get('completion_checks')
    problems = (completed.get('issues', []) if completed is not None else
                (run_metadata.get('execution_checkpoint') or {}).get('completion_issues', []))
    issues = list(dict.fromkeys(str(issue) for problem in problems
        if problem.get('artifact_id') in (None, str(record.id)) for issue in problem.get('issues', [])))
    if issues:
        metadata['completion_review'] = {'status': 'needs_revision', 'issues': issues,
            'scope': 'Automated completion review of this saved revision; not investigator approval.'}
    return AgentArtifact(
        id=str(record.id),
        type=record.type,
        title=record.title,
        data=record.payload or {},
        metadata=metadata,
    )


_validation_views = OrderedDict()
_validation_view_lock = RLock()
_validation_view_bytes = 0


def _checked_artifact_metadata(saved, sources, accessible, *, canonical_digest):
    """Bounded metadata-only cache. Call only after run/source access has been checked."""
    from services.agent.claim_validation import apply_claim_validation, validation_signature
    global _validation_view_bytes
    signature = validation_signature(saved, sources, accessible, canonical_digest=canonical_digest)
    if saved['metadata'].get('claim_validation_signature') == signature:
        return saved['metadata']
    key = (saved['id'], signature)
    # Serialize cache misses to avoid a polling stampede rechecking the same draft.
    with _validation_view_lock:
        cached = _validation_views.get(key)
        if cached is not None:
            _validation_views.move_to_end(key)
            return copy.deepcopy(cached[0])
        apply_claim_validation(saved, sources, accessible)
        metadata = saved['metadata']
        size = len(json.dumps(metadata, ensure_ascii=False).encode('utf8'))
        if size <= 512 * 1024:
            _validation_views[key] = (copy.deepcopy(metadata), size)
            _validation_view_bytes += size
            while len(_validation_views) > 128 or _validation_view_bytes > 8 * 1024 * 1024:
                _, (_, removed) = _validation_views.popitem(last=False)
                _validation_view_bytes -= removed
        return metadata


def artifact_views(db: Session, records, user, *, available=None) -> list[AgentArtifact]:
    """Refresh dependency notices from accessible revisions without altering saved content."""
    from services.agent.deliverables import dependency_metadata
    records = readable_artifacts(db, list(records), user)
    if not records:
        return []
    if available is None:
        thread_ids = {record.thread_id for record in records}
        available = db.query(AgentArtifactRecord).filter(AgentArtifactRecord.thread_id.in_(thread_ids)).all()
    accessible = readable_artifacts(db, available, user)
    by_thread = {}
    for record in accessible:
        by_thread.setdefault(record.thread_id, {})[str(record.id)] = to_api_artifact(record).model_dump()
    views, source_digests = [], {}
    for record in records:
        view = to_api_artifact(record)
        saved = view.model_dump()
        if 'claim_evidence' in view.metadata:
            from services.agent.claim_validation import canonical_source_fingerprint
            sources = ((record.run.extra_metadata or {}).get('execution_checkpoint') or {}).get('result_store', {}) if record.run else {}
            run_key = record.run_id
            if run_key not in source_digests:
                source_digests[run_key] = canonical_source_fingerprint(sources)
            saved['metadata'] = _checked_artifact_metadata(saved, sources, by_thread.get(record.thread_id, {}),
                                                          canonical_digest=source_digests[run_key])
        view.metadata = dependency_metadata(saved, by_thread.get(record.thread_id, {}))
        # Completion state is live run metadata, never a cached content check.
        view.metadata.pop('completion_review', None)
        completion_review = to_api_artifact(record).metadata.get('completion_review')
        if completion_review:
            view.metadata['completion_review'] = completion_review
        from services.agent.source_presentation import present_sources
        sources = ((record.run.extra_metadata or {}).get('execution_checkpoint') or {}).get('result_store', {}) if record.run else {}
        view.data = present_sources(view.data, sources)
        views.append(view)
    return views


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
        artifacts=artifact_views(db, run.artifacts, user),
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
        "steering": steering_view(run),
    }


def steering_view(run: AgentRun) -> dict[str, Any]:
    """The run's tool switches as the agent page shows them (services.agent.tool_groups)."""
    from services.agent import tool_groups
    meta = run.extra_metadata or {}
    requested = [e for e in meta.get("steering") or [] if isinstance(e, dict)]
    applied = [e for e in meta.get("steering_applied") or [] if isinstance(e, dict)]
    taken = {e.get("id") for e in applied}
    pending = [tool_groups.trail_entry(e) for e in requested if e.get("id") not in taken]
    return {"chosen": list(meta.get("tool_groups_chosen") or []), "applied": applied, "pending": pending,
            "off": sorted(tool_groups.off_groups([*applied, *[e for e in requested if e.get("id") not in taken]]))}


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
            "steering": fields["steering"],
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
    visible_messages = []
    for message in thread.messages:
        if message.run is not None and message.role == 'assistant':
            try:
                check_run_source_access(db, message.run, user)
            except PermissionError:
                continue
        visible_messages.append(message)
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
        for message in visible_messages
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
        artifacts=artifact_views(db, thread.artifacts, user, available=thread.artifacts),
    )
