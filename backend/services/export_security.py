from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from postgres.models.user import User
from services.system_log_service import LogOrigin, LogType, system_log_service


def correlation_id_from_request(request: Request | None) -> str:
    if request is None:
        return str(uuid.uuid4())
    header_value = request.headers.get("x-correlation-id") or request.headers.get("x-request-id")
    return header_value.strip() if header_value and header_value.strip() else str(uuid.uuid4())


def parse_case_uuid(case_id: str | UUID) -> UUID:
    if isinstance(case_id, UUID):
        return case_id
    return UUID(str(case_id))


def deterministic_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audit_export_event(
    *,
    db: Session,
    user: User,
    action: str,
    case_id: str | UUID | None,
    export_type: str,
    result: str,
    correlation_id: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    scope: dict[str, Any] | None = None,
    row_count: int | None = None,
    content_hash: str | None = None,
    content_type: str | None = None,
    error_class: str | None = None,
    success: bool | None = None,
) -> None:
    details: dict[str, Any] = {
        "case_id": str(case_id) if case_id is not None else None,
        "export_type": export_type,
        "result": result,
        "correlation_id": correlation_id,
    }
    if resource_type is not None:
        details["resource_type"] = resource_type
    if resource_id is not None:
        details["resource_id"] = str(resource_id)
    if scope is not None:
        details["scope"] = scope
    if row_count is not None:
        details["row_count"] = row_count
    if content_hash is not None:
        details["content_hash"] = content_hash
    if content_type is not None:
        details["content_type"] = content_type
    if error_class is not None:
        details["error_class"] = error_class

    system_log_service.log(
        LogType.USER_ACTION,
        LogOrigin.BACKEND,
        action,
        details=details,
        user=user.email,
        success=(result == "success") if success is None else success,
        error=error_class if result != "success" else None,
        db=db,
    )
