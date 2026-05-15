export type TriageStageType = "scan" | "classify" | "profile" | "custom" | string
export type TriageStageStatus = "pending" | "running" | "completed" | "failed" | string

export interface TriageStage {
  id: string
  order: number
  name: string
  type: TriageStageType
  status: TriageStageStatus
  config?: Record<string, unknown>
  created_at?: string | null
  started_at?: string | null
  completed_at?: string | null
  files_total?: number
  files_processed?: number
  files_failed?: number
  error?: string | null
}

export interface TriageCase {
  id: string
  name: string
  description: string
  source_path: string
  status: string
  created_at: string
  updated_at: string
  created_by: string
  stages: TriageStage[]
  scan_stats?: Partial<ScanStats>
  scan_cursor?: string | null
  profile?: TriageProfile
}

export interface DirectoryEntry {
  name: string
  is_dir: boolean
  path: string
}

export interface DirectoryBrowseResponse {
  current_path: string
  parent_path: string | null
  entries: DirectoryEntry[]
}

export interface ScanStats {
  total_files: number
  total_size: number
  os_detected: string | null
  by_category: Record<string, number>
  by_category_size: Record<string, number>
  by_extension: Record<string, number>
  extension_mismatches: number
  unique_hashes: number
}

export interface ClassificationStats {
  total_classified: number
  known_good: number
  known_bad: number
  unknown: number
  suspicious: number
  custom_match: number
  system_files: number
  user_files: number
  user_accounts: string[]
}

export interface TriageFile {
  id: string
  relative_path: string
  filename: string
  extension?: string | null
  size: number
  sha256?: string | null
  mime_type?: string | null
  magic_type?: string | null
  extension_mismatch: boolean
  category?: string | null
  subcategory?: string | null
  hash_classification?: string | null
  hash_source?: string | null
  is_system_file?: boolean | null
  is_user_file?: boolean | null
  user_account?: string | null
  created_time?: string | null
  modified_time?: string | null
  accessed_time?: string | null
  original_path?: string | null
}

export interface TriageFileListParams {
  skip?: number
  limit?: number
  sort_by?: string
  sort_dir?: "asc" | "desc"
  category?: string
  extension?: string
  hash_classification?: string
  search?: string
  path_prefix?: string
  is_system_file?: boolean
  is_user_file?: boolean
  user_account?: string
}

export interface TriageFileListResponse {
  files: TriageFile[]
  total: number
  skip: number
  limit: number
}

export interface ProcessorInfo {
  name: string
  display_name: string
  description: string
  input_types: string[]
  output_types: string[]
  requires_llm: boolean
  config_schema?: Record<string, unknown>
}

export interface Artifact {
  id: string
  stage_id?: string | null
  processor_name?: string | null
  artifact_type: string
  content?: string | null
  metadata?: Record<string, unknown>
  created_at?: string | null
  source_file_path?: string | null
  source_path?: string | null
  error?: string | null
}

export interface TriageTemplate {
  id: string
  name: string
  description: string
  created_by: string
  created_at: string
  stage_count: number
  stages?: TriageStage[]
}

export interface AdvisorSuggestion {
  action?: string
  detail?: string
  priority?: "high" | "medium" | "low" | string
  processor?: string
  stage_type?: string
  [key: string]: unknown
}

export interface TriageProfile {
  total_files: number
  total_size: number
  os_detected?: string | null
  classification?: Partial<ClassificationStats>
  by_category?: Record<string, unknown> | Array<Record<string, unknown>>
  timeline?: Array<Record<string, unknown>>
  user_profiles?: Array<Record<string, unknown>>
  high_value_artifacts?: Array<Record<string, unknown>>
  extension_mismatches?: Array<Record<string, unknown>>
}

export interface BackgroundTask {
  id: string
  task_type: string
  task_name: string
  owner?: string | null
  case_id?: string | null
  status: string
  created_at: string
  updated_at: string
  started_at?: string | null
  completed_at?: string | null
  progress: {
    total?: number
    completed?: number
    progress_total?: number
    progress_completed?: number
    [key: string]: unknown
  }
  error?: string | null
  metadata: Record<string, unknown>
}

export interface IngestPreview {
  file_count: number
  total_size: number
  artifact_count?: number
  files?: Array<Record<string, unknown>>
}
