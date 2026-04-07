export interface EvidenceFile {
  id: string
  original_filename: string
  stored_path: string
  size: number
  sha256: string
  status: string
  processing_stale?: boolean
  duplicate_of?: string | null
  created_at: string
  processed_at?: string | null
  last_error?: string | null
  summary?: string | null
  entity_count?: number
  engine_job_id?: string | null
}

export interface IngestionResult {
  file_id: string
  status: string
  entities_extracted: number
  relationships_extracted: number
  processing_time_ms: number
}

// Processing Profiles
export interface SpecialEntityType {
  name: string
  description?: string | null
}

export interface ProcessingProfile {
  name: string
  description?: string
  context_instructions?: string | null
  mandatory_instructions?: string[]
  special_entity_types?: SpecialEntityType[]
}

export interface ProfileSaveData {
  name: string
  description?: string | null
  context_instructions?: string | null
  mandatory_instructions?: string[]
  special_entity_types?: SpecialEntityType[]
}

// Background Tasks
export interface TaskFile {
  file_id?: string
  filename: string
  status: string
  error?: string | null
}

export interface TaskProgress {
  total: number
  completed: number
  failed?: number
}

export interface BackgroundTask {
  id: string
  task_name: string
  task_type: string
  status: "pending" | "running" | "completed" | "failed" | "cancelled"
  case_id?: string
  owner?: string
  progress?: TaskProgress
  files?: TaskFile[]
  error?: string | null
  metadata?: Record<string, unknown>
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

// Filesystem
export interface FilesystemItem {
  name: string
  path: string
  type: "file" | "directory"
  size?: number
  modified?: string
}

// Video Frames
export interface VideoFrame {
  frame_number: number
  filename: string
  timestamp: number
  timestamp_str: string
}

// Ingestion Logs
export interface IngestionLog {
  timestamp: string
  level: string
  message: string
  file?: string
  [key: string]: unknown
}

// Wiretap
export interface WiretapCheckResult {
  is_wiretap: boolean
  folder_path: string
  subfolders?: string[]
  file_count?: number
}

// LLM Config
export interface LLMModel {
  id: string
  name: string
  provider: string
  description?: string
  pros?: string[]
  cons?: string[]
  context_window?: number
}

// Evidence Summary
export interface EvidenceSummary {
  has_summary: boolean
  summary?: string | null
  filename?: string
}

// Folder types
export interface EvidenceFolder {
  id: string
  case_id: string
  name: string
  parent_id: string | null
  disk_path: string | null
  file_count: number
  subfolder_count: number
  has_profile: boolean
  created_at: string | null
  updated_at: string | null
}

export interface FolderTreeNode {
  id: string
  name: string
  parent_id: string | null
  file_count: number
  subfolder_count: number
  has_profile: boolean
  children: FolderTreeNode[]
}

export interface FolderContentsResponse {
  folder: {
    id: string
    name: string
    parent_id: string | null
    has_profile: boolean
  } | null
  breadcrumbs: { id: string; name: string }[]
  folders: EvidenceFolder[]
  files: EvidenceFileRecord[]
}

export interface EvidenceFileRecord {
  id: string
  case_id: string
  folder_id: string | null
  original_filename: string
  stored_path: string
  size: number
  sha256: string
  status: "unprocessed" | "processing" | "processed" | "failed"
  processing_stale: boolean
  is_duplicate: boolean
  duplicate_of: string | null
  is_relevant: boolean
  owner: string | null
  created_at: string | null
  processed_at: string | null
  last_error: string | null
  legacy_id: string | null
  summary: string | null
  entity_count: number | null
  relationship_count: number | null
  last_processed_folder_id: string | null
}

// Folder profiles
export interface FolderProfile {
  context_instructions: string | null
  mandatory_instructions: string[]
  profile_overrides: ProfileOverrides | null
}

export interface ProfileOverrides {
  special_entity_types?: { name: string; description?: string | null }[]
}

export interface ProfileChainLink {
  scope?: "case" | "folder"
  folder_id: string | null
  folder_name: string
  context_instructions: string | null
  mandatory_instructions?: string[]
  profile_overrides: ProfileOverrides | null
  source_profile_name?: string | null
}

export interface EffectiveProfile {
  chain: ProfileChainLink[]
  effective_context: string
  effective_mandatory_instructions: string[]
  effective_special_entity_types: { name: string; description?: string }[]
  merged_context: string
  merged_overrides: ProfileOverrides
}

// Job progress (from WebSocket)
export interface JobProgressMessage {
  job_id: string
  status: string
  progress: number
  message: string
}

export type PipelineStage =
  | "pending"
  | "extracting_text"
  | "generating_document_summary"
  | "chunking"
  | "extracting_entities"
  | "consolidating_entities"
  | "resolving_entities"
  | "resolving_relationships"
  | "generating_summaries"
  | "writing_graph"
  | "completed"
  | "failed"

export interface EvidenceJob {
  id: string
  case_id: string
  batch_id: string | null
  file_name: string
  status: PipelineStage
  progress: number
  message?: string
  error_message: string | null
  entity_count: number
  relationship_count: number
  file_size: number
  mime_type: string | null
  sha256: string | null
  created_at: string
  updated_at: string
}

// Profile templates
export interface ProfileTemplate {
  id: string
  name: string
  description: string
  context_instructions: string
  profile_overrides?: ProfileOverrides
}

export interface CaseProcessingProfile {
  source_profile_name: string | null
  source_profile_exists: boolean
  context_instructions: string | null
  mandatory_instructions: string[]
  special_entity_types: SpecialEntityType[]
}
