"""
File management routes — list, serve, and delete evidence files.
"""

import logging
import os
import shutil
import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db
from app.models.job import Job
from app.schemas.job import JobResponse

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer(auto_error=False)


def _extract_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    if credentials and credentials.credentials:
        return credentials.credentials

    token = request.cookies.get("access_token")
    if token:
        return token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing token",
    )


async def _get_current_user_row(
    db: AsyncSession,
    token: str,
) -> Mapping[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret_key,
            algorithms=[settings.auth_algorithm],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    email = payload.get("sub")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    result = await db.execute(
        text(
            """
            SELECT id, global_role, is_active
            FROM users
            WHERE email = :email
            LIMIT 1
            """
        ),
        {"email": email},
    )
    user = result.mappings().one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    return user


def _has_case_view_permission(permissions: dict[str, Any] | None) -> bool:
    case_permissions = (permissions or {}).get("case", {})
    return bool(case_permissions.get("view"))


async def _require_case_view(
    db: AsyncSession,
    case_id: str,
    user: Mapping[str, Any],
) -> None:
    try:
        case_uuid = uuid.UUID(str(case_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Case access denied",
        ) from exc

    case_result = await db.execute(
        text("SELECT id FROM cases WHERE id = :case_id LIMIT 1"),
        {"case_id": case_uuid},
    )
    if not case_result.mappings().one_or_none():
        raise HTTPException(status_code=404, detail="Case not found")

    global_role = getattr(user["global_role"], "value", user["global_role"])
    if global_role == "super_admin":
        return

    membership_result = await db.execute(
        text(
            """
            SELECT permissions
            FROM case_memberships
            WHERE case_id = :case_id AND user_id = :user_id
            LIMIT 1
            """
        ),
        {"case_id": case_uuid, "user_id": user["id"]},
    )
    membership = membership_result.mappings().one_or_none()
    if not membership or not _has_case_view_permission(membership["permissions"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have case.view permission for this case",
        )


@router.get("/cases/{case_id}/files", response_model=list[JobResponse])
async def list_files(
    case_id: str,
    token: str = Depends(_extract_token),
    db: AsyncSession = Depends(get_db),
):
    """List all uploaded files (jobs) for a case, ordered by creation date descending."""
    current_user = await _get_current_user_row(db, token)
    await _require_case_view(db, case_id, current_user)

    result = await db.execute(
        select(Job)
        .where(Job.case_id == case_id)
        .order_by(Job.created_at.desc())
    )
    jobs = result.scalars().all()
    return jobs


@router.get("/cases/{case_id}/files/{job_id}")
async def serve_file(
    case_id: str,
    job_id: str,
    token: str = Depends(_extract_token),
    db: AsyncSession = Depends(get_db),
):
    """Serve/download an evidence file by job ID."""
    current_user = await _get_current_user_row(db, token)

    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.case_id == case_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="File not found")

    await _require_case_view(db, job.case_id, current_user)

    if not os.path.exists(job.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    media_type = job.mime_type or "application/octet-stream"

    return FileResponse(
        path=job.file_path,
        filename=job.file_name,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{job.file_name}"',
        },
    )


@router.delete("/cases/{case_id}/files/{job_id}", status_code=204)
async def delete_file(
    case_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete an evidence file from storage and its job record.

    Note: Neo4j/ChromaDB cleanup is the backend's responsibility.
    This only removes the physical file and the job record.
    """
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.case_id == case_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="File not found")

    # Delete file from disk
    if os.path.exists(job.file_path):
        try:
            os.remove(job.file_path)
            # Remove the job directory if empty
            job_dir = os.path.dirname(job.file_path)
            if os.path.isdir(job_dir) and not os.listdir(job_dir):
                shutil.rmtree(job_dir, ignore_errors=True)
        except OSError as e:
            logger.warning("Failed to delete file %s: %s", job.file_path, e)

    # Delete job record
    await db.delete(job)
    await db.commit()
