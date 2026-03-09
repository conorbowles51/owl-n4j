export interface EvidenceFile {
  id: string
  original_filename: string
  stored_path: string
  size: number
  sha256: string
  status: string
  duplicate_of?: string | null
  created_at: string
  processed_at?: string | null
  last_error?: string | null
  summary?: string | null
  entity_count?: number
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
  case_type?: string | null
  provider?: string
  model?: string
  settings?: Record<string, unknown>
}

export interface ProfileDetail {
  name: string
  description?: string
  case_type?: string | null
  ingestion?: {
    system_context?: string
    special_entity_types?: SpecialEntityType[]
    temperature?: number
  }
  chat?: {
    system_context?: string
    analysis_guidance?: string
    temperature?: number
  }
  llm_config?: {
    provider?: string
    model_id?: string
  }
  folder_processing?: Record<string, unknown> | null
}

export interface ProfileSaveData {
  name: string
  description: string
  case_type?: string | null
  ingestion_system_context?: string | null
  special_entity_types?: SpecialEntityType[]
  ingestion_temperature?: number
  llm_provider?: string
  llm_model_id?: string
  chat_system_context?: string | null
  chat_analysis_guidance?: string | null
  chat_temperature?: number
  folder_processing?: Record<string, unknown> | null
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
