"""
Pydantic models for the Triage API.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel


# ── Requests ───────────────────────────────────────────────────────────

class CreateTriageCaseRequest(BaseModel):
    name: str
    description: str = ""
    source_path: str


class StartScanRequest(BaseModel):
    resume: bool = False


class FileListParams(BaseModel):
    skip: int = 0
    limit: int = 50
    sort_by: str = "relative_path"
    sort_dir: str = "asc"
    category: Optional[str] = None
    extension: Optional[str] = None
    hash_classification: Optional[str] = None
    search: Optional[str] = None
    path_prefix: Optional[str] = None
    is_system_file: Optional[bool] = None
    is_user_file: Optional[bool] = None
    user_account: Optional[str] = None


# ── Stage / Processor requests ─────────────────────────────────────────

class CreateStageRequest(BaseModel):
    name: str
    processor_name: str
    config: Dict[str, Any] = {}
    file_filter: Dict[str, Any] = {}


class ExecuteStageRequest(BaseModel):
    max_workers: Optional[int] = None


class UploadHashSetRequest(BaseModel):
    name: str
    hashes: List[str]


# ── Template requests ──────────────────────────────────────────────────

class CreateTemplateRequest(BaseModel):
    name: str
    description: str = ""


class ApplyTemplateRequest(BaseModel):
    template_id: str


# ── Advisor requests ───────────────────────────────────────────────────

class AdvisorChatRequest(BaseModel):
    question: str
    model_provider: Optional[str] = None
    model_id: Optional[str] = None


# ── Ingest requests ───────────────────────────────────────────────────

class IngestRequest(BaseModel):
    target_case_id: str
    file_ids: List[str] = []
    include_artifacts: bool = True
    file_filter: Optional[Dict[str, Any]] = None


# ── Responses ──────────────────────────────────────────────────────────

class StageResponse(BaseModel):
    id: str
    order: int
    name: str
    type: str
    status: str
    config: Dict[str, Any] = {}
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    files_total: int = 0
    files_processed: int = 0
    files_failed: int = 0
    error: Optional[str] = None


class TriageCaseResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    source_path: str
    status: str
    created_at: str
    updated_at: str
    created_by: str
    stages: List[StageResponse] = []
    scan_stats: Dict[str, Any] = {}


class TriageFileResponse(BaseModel):
    id: str
    relative_path: str
    filename: str
    extension: Optional[str] = None
    size: int = 0
    sha256: Optional[str] = None
    mime_type: Optional[str] = None
    magic_type: Optional[str] = None
    extension_mismatch: bool = False
    category: Optional[str] = None
    subcategory: Optional[str] = None
    hash_classification: Optional[str] = None
    hash_source: Optional[str] = None
    is_system_file: Optional[bool] = None
    is_user_file: Optional[bool] = None
    user_account: Optional[str] = None
    created_time: Optional[str] = None
    modified_time: Optional[str] = None
    accessed_time: Optional[str] = None
    original_path: Optional[str] = None


class TriageFileListResponse(BaseModel):
    files: List[TriageFileResponse]
    total: int
    skip: int
    limit: int


class ScanStatsResponse(BaseModel):
    total_files: int = 0
    total_size: int = 0
    os_detected: Optional[str] = None
    by_category: Dict[str, int] = {}
    by_category_size: Dict[str, int] = {}
    by_extension: Dict[str, int] = {}
    extension_mismatches: int = 0
    unique_hashes: int = 0


class ClassificationStatsResponse(BaseModel):
    total_classified: int = 0
    known_good: int = 0
    known_bad: int = 0
    unknown: int = 0
    suspicious: int = 0
    custom_match: int = 0
    system_files: int = 0
    user_files: int = 0
    user_accounts: List[str] = []


class ProcessorInfo(BaseModel):
    name: str
    display_name: str
    description: str
    input_types: List[str] = []
    output_types: List[str] = []
    requires_llm: bool = False
    config_schema: Dict[str, Any] = {}


class ArtifactResponse(BaseModel):
    id: str
    stage_id: Optional[str] = None
    processor_name: Optional[str] = None
    artifact_type: str
    content: Optional[str] = None
    metadata: Dict[str, Any] = {}
    created_at: Optional[str] = None
    source_file_path: Optional[str] = None


class ProvenanceResponse(BaseModel):
    file: TriageFileResponse
    stages: List[StageResponse] = []
    artifacts: List[ArtifactResponse] = []


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    created_by: str
    created_at: str
    stage_count: int = 0


class ProfileResponse(BaseModel):
    total_files: int = 0
    total_size: int = 0
    os_detected: Optional[str] = None
    classification: ClassificationStatsResponse = ClassificationStatsResponse()
    by_category: Dict[str, Any] = {}
    timeline: List[Dict[str, Any]] = []
    user_profiles: List[Dict[str, Any]] = []
    high_value_artifacts: List[Dict[str, Any]] = []
    extension_mismatches: List[Dict[str, Any]] = []
