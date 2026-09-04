from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import require_case_view
from routers.users import get_current_db_user
from services.workspace_attention_service import (
    WorkspaceAttentionValidationError,
    clear_personal_attention_state,
    get_workspace_overview,
    set_personal_attention_state,
)


router = APIRouter(prefix="/api/workspace", tags=["workspace-overview"])


class AttentionStateRequest(BaseModel):
    action: Literal["dismiss", "snooze"]
    snoozed_until: datetime | None = None


@router.get("/{case_id}/overview")
def read_workspace_overview(
    case_id: UUID,
    timezone_name: str | None = Query(None, alias="timezone", max_length=128),
    _authorized_case_id: UUID = Depends(require_case_view),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return get_workspace_overview(
            db,
            case_id=case_id,
            user=current_user,
            timezone_name=timezone_name,
        )
    except WorkspaceAttentionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{case_id}/attention/{attention_key:path}")
def update_personal_attention(
    case_id: UUID,
    attention_key: str,
    payload: AttentionStateRequest,
    _authorized_case_id: UUID = Depends(require_case_view),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return set_personal_attention_state(
            db,
            case_id=case_id,
            user=current_user,
            attention_key=unquote(attention_key),
            action=payload.action,
            snoozed_until=payload.snoozed_until,
        )
    except WorkspaceAttentionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/{case_id}/attention/{attention_key:path}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def clear_personal_attention(
    case_id: UUID,
    attention_key: str,
    _authorized_case_id: UUID = Depends(require_case_view),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    clear_personal_attention_state(
        db,
        case_id=case_id,
        user=current_user,
        attention_key=unquote(attention_key),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
