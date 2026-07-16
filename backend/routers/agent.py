from __future__ import annotations

import json
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
import services.agent.storage as agent_storage
from services.agent.schemas import (
    AgentArtifact,
    AgentArtifactListResponse,
    AgentArtifactMutationResponse,
    AgentArtifactRecycleRequest,
    AgentArtifactRenameRequest,
    AgentArtifactUpdateRequest,
    AgentMessageRequest,
    AgentMessageResponse,
    AgentRunDetail,
    AgentRunStatusResponse,
    AgentThreadDetail,
    AgentThreadSummary,
)
from services.agent.service import agent_service
from services.case_service import CaseAccessDenied, CaseNotFound


router = APIRouter(prefix="/api/agent", tags=["agent"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _raise_case_artifact_http_error(exc: Exception) -> None:
    if isinstance(exc, agent_storage.ArtifactConcurrencyError):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "artifact version conflict",
                "current_version": exc.current_version,
            },
        ) from exc
    if isinstance(exc, agent_storage.ArtifactValidationError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, (agent_storage.ArtifactNotFoundError, CaseNotFound)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, (CaseAccessDenied, PermissionError)):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    raise exc


@router.get("/threads", response_model=list[AgentThreadSummary])
async def list_agent_threads(
    case_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return agent_service.list_threads(db=db, user=current_user, case_id=case_id)
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/threads/{thread_id}", response_model=AgentThreadDetail)
async def get_agent_thread(
    thread_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return agent_service.get_thread(db=db, user=current_user, thread_id=thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/messages", response_model=AgentMessageResponse)
async def create_agent_message(
    request: AgentMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return agent_service.handle_message(db=db, user=current_user, request=request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/messages/stream")
async def stream_agent_message(
    request: AgentMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        events = agent_service.stream_message(db=db, user=current_user, request=request)
        event_iterator = iter(events)
        first_event = next(event_iterator)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except StopIteration as exc:
        raise HTTPException(status_code=500, detail="Agent stream ended before it started") from exc

    def event_stream():
        yield _sse(first_event)
        try:
            for event in event_iterator:
                yield _sse(event)
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/runs/{run_id}", response_model=AgentRunDetail)
async def get_agent_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return agent_service.get_run(db=db, user=current_user, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/costs/summary")
async def get_agent_cost_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    return agent_service.get_cost_summary(db=db, user=current_user)


@router.post("/runs/{run_id}:cancel", response_model=AgentRunStatusResponse)
async def cancel_agent_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return agent_service.cancel_run(db=db, user=current_user, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/cases/{case_id}/artifacts", response_model=AgentArtifactListResponse)
async def list_case_agent_artifacts(
    case_id: UUID,
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return agent_service.list_case_artifacts(
            db=db,
            user=current_user,
            case_id=case_id,
            include_deleted=include_deleted,
        )
    except Exception as exc:
        _raise_case_artifact_http_error(exc)


@router.get("/cases/{case_id}/artifacts/{artifact_id}", response_model=AgentArtifact)
async def open_case_agent_artifact(
    case_id: UUID,
    artifact_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return agent_service.open_case_artifact(
            db=db,
            user=current_user,
            case_id=case_id,
            artifact_id=artifact_id,
        )
    except Exception as exc:
        _raise_case_artifact_http_error(exc)


@router.patch("/cases/{case_id}/artifacts/{artifact_id}/rename", response_model=AgentArtifactMutationResponse)
async def rename_case_agent_artifact(
    case_id: UUID,
    artifact_id: UUID,
    request: AgentArtifactRenameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return agent_service.rename_case_artifact(
            db=db,
            user=current_user,
            case_id=case_id,
            artifact_id=artifact_id,
            request=request,
        )
    except Exception as exc:
        _raise_case_artifact_http_error(exc)


@router.patch("/cases/{case_id}/artifacts/{artifact_id}", response_model=AgentArtifactMutationResponse)
async def update_case_agent_artifact(
    case_id: UUID,
    artifact_id: UUID,
    request: AgentArtifactUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return agent_service.update_case_artifact(
            db=db,
            user=current_user,
            case_id=case_id,
            artifact_id=artifact_id,
            request=request,
        )
    except Exception as exc:
        _raise_case_artifact_http_error(exc)


@router.post("/cases/{case_id}/artifacts/{artifact_id}/recycle", response_model=AgentArtifactMutationResponse)
async def recycle_case_agent_artifact(
    case_id: UUID,
    artifact_id: UUID,
    request: AgentArtifactRecycleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return agent_service.recycle_case_artifact(
            db=db,
            user=current_user,
            case_id=case_id,
            artifact_id=artifact_id,
            request=request,
        )
    except Exception as exc:
        _raise_case_artifact_http_error(exc)


@router.post("/artifacts/{artifact_id}:approve", response_model=AgentArtifact)
async def approve_agent_artifact(
    artifact_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return agent_service.approve_artifact(
            db=db,
            user=current_user,
            artifact_id=artifact_id,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/artifacts/{artifact_id}:revert", response_model=AgentArtifact)
async def revert_agent_artifact_to_draft(
    artifact_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return agent_service.revert_artifact_to_draft(
            db=db,
            user=current_user,
            artifact_id=artifact_id,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/artifacts/{artifact_id}/export")
async def export_agent_artifact(
    artifact_id: UUID,
    case_id: UUID = Query(...),
    format: Literal["csv", "pdf", "docx"] = Query(default="csv"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        exported = agent_service.export_artifact(
            db=db,
            user=current_user,
            case_id=case_id,
            artifact_id=artifact_id,
            export_format=format,
        )
        ascii_filename = exported.filename.encode("ascii", "ignore").decode("ascii") or "agent-artifact.csv"
        disposition = (
            f'attachment; filename="{ascii_filename}"; '
            f"filename*=UTF-8''{quote(exported.filename)}"
        )
        return Response(
            content=exported.content,
            media_type=exported.media_type,
            headers={
                "Content-Disposition": disposition,
                "X-Agent-Export-Format": format,
            },
        )
    except Exception as exc:
        _raise_case_artifact_http_error(exc)
