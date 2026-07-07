"""Admin platform self-update endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from postgres.models.user import User
from routers.users import require_admin
from services.platform_update_service import PlatformUpdateError, platform_update_service


router = APIRouter(prefix="/api/admin/update", tags=["admin-update"])


class PlatformUpdateStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    config_error: str | None = None
    can_deploy: bool
    repo_dir: str
    remote: str
    branch: str | None = None
    service_name: str
    local_sha: str | None = None
    local_short_sha: str | None = None
    remote_sha: str | None = None
    remote_short_sha: str | None = None
    update_available: bool
    last_checked_at: str | None = None
    last_check_error: str | None = None
    deployment_running: bool
    deployment_status: str
    deployment_error: str | None = None
    deployment_started_at: str | None = None
    deployment_completed_at: str | None = None
    last_deploy_requested_by: str | None = None
    deploy_log_path: str | None = None
    deploy_log_tail: str | None = None


def _current_user_label(user: User) -> str:
    return user.email or user.name or str(user.id)


@router.get("/status", response_model=PlatformUpdateStatusResponse)
def get_platform_update_status(_: User = Depends(require_admin)):
    return platform_update_service.get_status()


@router.post("/check", response_model=PlatformUpdateStatusResponse)
def check_platform_update(_: User = Depends(require_admin)):
    return platform_update_service.refresh_status()


@router.post("/deploy", response_model=PlatformUpdateStatusResponse)
def deploy_platform_update(current_user: User = Depends(require_admin)):
    try:
        return platform_update_service.trigger_deploy(
            requested_by=_current_user_label(current_user),
        )
    except PlatformUpdateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
