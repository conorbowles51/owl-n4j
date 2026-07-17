"""Shared HTTP case-authorization dependencies.

These guards authenticate with the database-backed user and authorize a
caller-supplied case identifier before a route handler can load or mutate
case data.  They intentionally run as FastAPI dependencies so authorization
errors cannot be swallowed by broad handler-level exception blocks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.case_service import CaseAccessDenied, CaseNotFound, check_case_access

CasePermission = tuple[str, str]
PermissionResolver = Callable[[Request, dict[str, Any]], CasePermission | None]


async def request_json_payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").lower()
    if not content_type.startswith("application/json"):
        return {}
    try:
        payload = await request.json()
    except (ValueError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def request_case_id(request: Request, payload: dict[str, Any]) -> str | None:
    value = request.path_params.get("case_id") or request.query_params.get("case_id")
    if value is None:
        value = payload.get("case_id")
    return str(value) if value not in (None, "") else None


def authorize_case(
    db: Session,
    case_id: str | UUID,
    current_user: User,
    permission: CasePermission,
) -> UUID:
    """Authorize one case and normalize security failures to HTTP responses."""
    try:
        case_uuid = case_id if isinstance(case_id, UUID) else UUID(case_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid case_id",
        ) from exc

    try:
        check_case_access(
            db,
            case_uuid,
            current_user,
            required_permission=permission,
        )
    except CaseNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        ) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        ) from exc
    return case_uuid


def case_access_dependency(
    permission_resolver: PermissionResolver,
):
    """Build a router dependency that guards requests carrying ``case_id``."""

    async def require_request_case_access(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_db_user),
    ) -> None:
        payload = await request_json_payload(request)
        case_id = request_case_id(request, payload)
        permission = permission_resolver(request, payload)
        if case_id is None or permission is None:
            return
        authorize_case(db, case_id, current_user, permission)

    return require_request_case_access
