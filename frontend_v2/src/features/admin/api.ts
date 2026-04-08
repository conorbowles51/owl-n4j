import { fetchAPI } from "@/lib/api-client"
import type { ProcessingProfile } from "@/types/evidence.types"

export type Profile = ProcessingProfile

export interface SetupStatus {
  needs_setup: boolean
}

export interface AICostUserOption {
  id: string
  name: string
  email: string
}

export interface AICostCaseOption {
  id: string
  title: string
}

export interface AICostFiltersResponse {
  users: AICostUserOption[]
  cases: AICostCaseOption[]
}

export interface AICostSummaryBreakdownItem {
  key: string
  label: string
  cost_usd: number
  request_count: number
}

export interface AICostSummaryResponse {
  total_cost_usd: number
  ingestion_cost_usd: number
  chat_cost_usd: number
  billable_calls: number
  top_models: AICostSummaryBreakdownItem[]
  top_users: AICostSummaryBreakdownItem[]
}

export interface AICostTimeseriesPoint {
  bucket_date: string
  ingestion_cost_usd: number
  chat_cost_usd: number
  total_cost_usd: number
}

export interface AICostTimeseriesResponse {
  points: AICostTimeseriesPoint[]
}

export interface AICostRecord {
  id: string
  created_at: string
  source: string
  operation_kind?: string | null
  provider: string
  model_id: string
  prompt_tokens?: number | null
  completion_tokens?: number | null
  total_tokens?: number | null
  cost_usd: number
  pricing_version?: string | null
  description?: string | null
  user_id?: string | null
  user_name?: string | null
  user_email?: string | null
  case_id?: string | null
  case_title?: string | null
  engine_job_id?: string | null
  evidence_file_id?: string | null
  evidence_file_name?: string | null
  conversation_id?: string | null
  extra_metadata?: Record<string, unknown> | null
}

export interface AICostRecordsResponse {
  records: AICostRecord[]
  total_count: number
  total_cost_usd: number
  page: number
  page_size: number
}

export const profilesAPI = {
  list: () => fetchAPI<Profile[]>("/api/profiles"),

  get: (profileName: string) =>
    fetchAPI<Profile>(`/api/profiles/${encodeURIComponent(profileName)}`),

  save: (profileData: Profile) =>
    fetchAPI<Profile>("/api/profiles", {
      method: "POST",
      body: profileData,
    }),

  delete: (profileName: string) =>
    fetchAPI<void>(`/api/profiles/${encodeURIComponent(profileName)}`, {
      method: "DELETE",
    }),
}

export const setupAPI = {
  getStatus: () => fetchAPI<SetupStatus>("/api/setup/status"),

  createInitialUser: (data: {
    email: string
    name: string
    password: string
  }) =>
    fetchAPI<void>("/api/setup/initial-user", {
      method: "POST",
      body: data,
    }),
}

function buildAIQuery(params: Record<string, string | number | undefined>) {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "" && value !== "all") {
      qs.set(key, String(value))
    }
  })
  return qs.toString()
}

export const aiCostsAPI = {
  getFilters: (params: {
    source?: string
    start_date?: string
    end_date?: string
  }) =>
    fetchAPI<AICostFiltersResponse>(
      `/api/admin/ai-costs/filters?${buildAIQuery(params)}`
    ),

  getSummary: (params: Record<string, string | number | undefined>) =>
    fetchAPI<AICostSummaryResponse>(
      `/api/admin/ai-costs/summary?${buildAIQuery(params)}`
    ),

  getTimeseries: (params: Record<string, string | number | undefined>) =>
    fetchAPI<AICostTimeseriesResponse>(
      `/api/admin/ai-costs/timeseries?${buildAIQuery(params)}`
    ),

  getRecords: (params: Record<string, string | number | undefined>) =>
    fetchAPI<AICostRecordsResponse>(
      `/api/admin/ai-costs/records?${buildAIQuery(params)}`
    ),
}
