import type { AIWorkloadModelConfig, LLMModel } from "@/types/evidence.types"

export interface AIProviderConnection {
  id: "openai" | "anthropic" | "gemini"
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
  status: "ready" | "needs_key"
  description: string
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
