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
from services.agent.schemas import (
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


@router.get("/artifacts/{artifact_id}/export")
async def export_agent_artifact(
    artifact_id: UUID,
    format: Literal["csv", "pdf", "docx"] = Query(default="csv"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        exported = agent_service.export_artifact(
            db=db,
            user=current_user,
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
                "X-Export-ID": exported.export_id,
            },
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
