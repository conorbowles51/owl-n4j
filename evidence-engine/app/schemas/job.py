import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.job import JobStatus


class JobCreate(BaseModel):
    llm_profile: str | None = None


class JobResponse(BaseModel):
    id: uuid.UUID
    case_id: str
    batch_id: uuid.UUID | None = None
    job_type: str = "ingestion"
    file_name: str | None = None
    status: JobStatus
    progress: float
    error_message: str | None
    entity_count: int
    relationship_count: int
    file_size: int = 0
    mime_type: str | None = None
    sha256: str | None = None
    document_summary: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobProgress(BaseModel):
    job_id: str
    status: str
    progress: float
    message: str
