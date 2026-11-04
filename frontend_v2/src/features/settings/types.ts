import type { AIWorkloadModelConfig, LLMModel } from "@/types/evidence.types"

export interface AIProviderConnection {
  id: "openai" | "anthropic" | "gemini" | "deepseek"
  display_name: string
  description: string
  configured: boolean
  status: "connected" | "invalid" | "unavailable" | "disconnected"
  source: "database" | "environment" | null
  key_last_four: string | null
  revision: number
  validated_at?: string | null
  validation_error_code?: string | null
  in_use_by: string[]
}

export interface AISupportingService {
  id: string
  label: string
  provider: string
  status: "ready" | "needs_key" | "down"
  description: string
  /** The state the last calls left (up, down with why and since when). Transcription: the OpenAI account's state, as
   *  the search embedding calls found it. */
  health?: AIServiceHealth
}

export interface AIServiceHealth {
  status: "up" | "down" | "unknown"
  reason?: string | null
  /** When the outage began; null when its start was not recorded (see first_recorded_failure_at). */
  down_since?: string | null
  down_since_known?: boolean
  /** The first failure the app recorded; the outage may have begun earlier when down_since_known is false. */
  first_recorded_failure_at?: string | null
  /** Transcription: the OpenAI account's last call that worked, which bounds when the refusals began. */
  failing_after?: string | null
  last_failure_at?: string | null
  last_success_at?: string | null
  failures_since_down?: number
  backfill_pending?: boolean
  /** What the outage means for this service; absent for search embeddings (searches use the words instead). */
  consequence?: string | null
}

export interface AISettings {
  policy_revision: number
  default_provider: string
  providers: AIProviderConnection[]
  models: LLMModel[]
  workloads: Record<string, { label: string; description: string; group: string }>
  routing: Record<string, AIWorkloadModelConfig>
  recommended_profiles: Record<string, Record<string, AIWorkloadModelConfig>>
  supporting_services: AISupportingService[]
  permissions: {
    can_edit_routing: boolean
    can_manage_credentials: boolean
  }
}

export interface ProviderTestResult {
  provider: string
  status: string
  available_models: string[]
  tested_at: string
}
