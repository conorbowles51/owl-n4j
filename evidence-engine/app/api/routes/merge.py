"""API route for entity merge jobs."""

import json
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.job import Job
from app.schemas.job import JobResponse

router = APIRouter()


class MergeEntityPayload(BaseModel):
    key: str
    name: str
    category: str | None = None
    specific_type: str | None = None
    summary: str | None = None
    description: str | None = None
    verified_facts: list[dict[str, Any]] | None = None
    ai_insights: list[dict[str, Any]] | None = None
    aliases: list[str] | None = None
    source_files: list[str] | None = None
    source_quotes: list[str] | None = None
    confidence: float | None = None
    properties: dict[str, Any] | None = None
    relationships: list[dict[str, Any]] | None = None


class UserPreferences(BaseModel):
    name: str | None = None
    type: str | None = None


class MergeEntitiesRequest(BaseModel):
    entities: list[MergeEntityPayload]
    user_preferences: UserPreferences | None = None
    requested_by_user_id: str | None = None


@router.post(
    "/cases/{case_id}/merge-entities",
    response_model=JobResponse,
    status_code=201,
)
async def merge_entities(
    case_id: str,
    body: MergeEntitiesRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a merge job that uses AI to merge multiple entities into one."""
    if len(body.entities) < 2:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="At least 2 entities required for merge")

    job_id = uuid.uuid4()
    requested_by = None
    if body.requested_by_user_id:
        try:
            requested_by = uuid.UUID(body.requested_by_user_id)
        except (ValueError, TypeError):
            pass

    entity_names = ", ".join(e.name for e in body.entities[:5])

    # Sanitize payload — PostgreSQL JSONB rejects \u0000 null bytes
    payload = body.model_dump(mode="json")
    payload_json = json.dumps(payload)
    payload_json = payload_json.replace("\x00", "").replace("\\u0000", "")
    payload = json.loads(payload_json)

    job = Job(
        id=job_id,
        case_id=case_id,
        job_type="entity_merge",
        merge_payload=payload,
        file_name=f"Merge: {entity_names[:200]}",
        file_path=None,
        requested_by_user_id=requested_by,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Enqueue merge worker
    pool = request.app.state.arq_pool
    await pool.enqueue_job("process_merge", str(job_id), case_id)

    return job
