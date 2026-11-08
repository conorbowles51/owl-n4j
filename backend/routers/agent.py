from __future__ import annotations

import json
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
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
from services.ai_budget import BudgetRefused
from services.case_service import CaseAccessDenied, CaseNotFound


router = APIRouter(prefix="/api/agent", tags=["agent"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/threads", response_model=list[AgentThreadSummary])
def list_agent_threads(
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


@router.get("/workflows")
def list_agent_workflows(
    case_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """The guided investigative workflows; with case_id, each one's readiness on that case's measured counts."""
    try:
        return agent_service.list_workflows(db=db, user=current_user, case_id=case_id)
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


_BOUND_TOOLS: list[str] = []


@router.get("/capabilities")
def list_agent_capabilities(current_user: User = Depends(get_current_db_user)):
    """What the case agent can work with, in plain words: each kind of case material, what it covers and example
    questions (services.agent.capabilities, the registry the coverage check uses). Kinds whose tools are not bound
    on this server are left out."""
    from services.agent.capabilities import capabilities
    from services.agent.tools import AgentToolContext, make_agent_tools
    if not _BOUND_TOOLS:
        _BOUND_TOOLS.extend(t.name for t in make_agent_tools(AgentToolContext(case_id="00000000-0000-0000-0000-000000000000")))
    return capabilities(_BOUND_TOOLS)


@router.get("/threads/{thread_id}", response_model=AgentThreadDetail)
def get_agent_thread(
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


@router.post("/threads/{thread_id}/adopt-current-mandate")
def adopt_current_agent_mandate(
    thread_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return agent_service.adopt_current_mandate(db=db, user=current_user, thread_id=thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/messages", response_model=AgentMessageResponse)
def create_agent_message(
    request: AgentMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return agent_service.handle_message(db=db, user=current_user, request=request)
    except BudgetRefused as exc:
        raise HTTPException(status_code=402, detail=exc.reason) from exc
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


def get_run_db():
    """The run's own session: a streamed run outlives its request (services.agent.live_runs), so its session is
    closed by the run's worker thread when the run ends, not when the response does. Closed here only when the
    run never started."""
    from postgres.session import _get_session_local
    db = _get_session_local()()
    try:
        yield db
    except BaseException:
        db.close()
        raise


@router.post("/messages/stream")
def stream_agent_message(
    request: AgentMessageRequest,
    db: Session = Depends(get_run_db),
    current_user: User = Depends(get_current_db_user),
):
    from services.agent import live_runs

    started = False
    try:
        user = db.get(User, current_user.id) or current_user
        live = live_runs.LiveRun()
        events = agent_service.stream_message(db=db, user=user, request=request, live=live)
        event_iterator = iter(events)
        first_event = next(event_iterator)
        started = True
    except BudgetRefused as exc:
        raise HTTPException(status_code=402, detail=exc.reason) from exc
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
    finally:
        if not started:
            db.close()

    # The run goes on to its end on its own thread; leaving the page stops only this reading of it.
    live_runs.pump(event_iterator, live, on_end=db.close, name=f"agent-run-{first_event.get('run_id')}")

    def event_stream():
        yield _sse(first_event)
        try:
            for event in live.read():
                yield _sse(event)
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})
        finally:
            live.reader_left()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/runs/active")
def list_active_agent_runs(
    case_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """This person's runs still working in the case, newest first, each with its plain progress line: what the
    agent page shows on return while a run goes on server-side."""
    try:
        return {"runs": agent_service.active_runs(db=db, user=current_user, case_id=case_id)}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/runs/{run_id}", response_model=AgentRunDetail)
def get_agent_run(
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


@router.get("/runs/{run_id}/record")
def get_agent_run_record(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """The run record: the disclosure record of one agent run (who, when, model, prompt version, every call)."""
    try:
        return agent_service.get_run_record(db=db, user=current_user, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/runs/{run_id}/record/export")
def export_agent_run_record(
    run_id: UUID,
    kind: Literal["strategy", "not_examined"] = Query(default="strategy"),
    format: Literal["csv", "pdf"] = Query(default="csv"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        exported = agent_service.export_run_record(db=db, user=current_user, run_id=run_id, kind=kind,
                                                   export_format=format)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    ascii_filename = exported.filename.encode("ascii", "ignore").decode("ascii") or "agent-run-record.csv"
    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{quote(exported.filename)}',
            "X-Agent-Export-Format": format,
        },
    )


@router.get("/costs/summary")
def get_agent_cost_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    return agent_service.get_cost_summary(db=db, user=current_user)


@router.post("/runs/{run_id}:cancel", response_model=AgentRunStatusResponse)
def cancel_agent_run(
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
def export_agent_artifact(
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


class AcceptAnswerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    dossier_id: UUID
    category: str = Field(min_length=1, max_length=128)


@router.post("/messages/{message_id}/accept-into-assessment", status_code=201)
def accept_answer_into_assessment(message_id: UUID, body: AcceptAnswerBody, db: Session = Depends(get_db),
                                  user: User = Depends(get_current_db_user)):
    """CO-18 (agent): a person accepts an agent answer into a dossier assessment, stored ai_assisted with "Read by
    <model>, accepted by <name>"; the records the answer cites become its supporting links."""
    from routers.case_access import authorize_case
    from services.agent import accept
    from services.dossier_service import DossierNotFound
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = accept.accept_answer_into_assessment(db, case_id=body.case_id, message_id=message_id,
                                                   dossier_id=body.dossier_id, category=body.category, user=user)
        db.commit()
        return out
    except (LookupError, DossierNotFound) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
