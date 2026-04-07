import type { EntityType } from "@/lib/theme"

export type ChatScope = "case_overview" | "selection"

export interface ChatSource {
  filename: string
  excerpt?: string
  page?: number
}

export interface ChatCost {
  usd: number
  prompt_tokens?: number | null
  completion_tokens?: number | null
  total_tokens?: number | null
  cost_record_id?: string | null
}

export interface ChatModelInfo {
  provider: string
  model_id: string
  model_name: string
  server: string
}

export interface ChatProvenance {
  case_id?: string
  case_revision_id?: string | null
  snapshot_id?: string | null
}

export interface ConversationSummary {
  id: string
  name: string
  timestamp: string
  created_at: string
  updated_at: string
  last_message_at: string
  owner_user_id: string
  case_id: string
  message_count: number
}

export interface Conversation {
  id: string
  name: string
  messages: ChatMessageData[]
  timestamp: string
  created_at: string
  updated_at: string
  last_message_at: string
  owner?: string | null
  owner_user_id: string
  snapshot_id?: string | null
  case_id: string
  case_revision_id?: string | null
  message_count: number
}

export interface CreateChatHistory {
  name?: string
  messages: ChatMessageData[]
  case_id: string
}

export interface ResultGraph {
  nodes: ResultGraphNode[]
  links: ResultGraphLink[]
}

export interface ChatMessageData {
  id?: string
  role: "user" | "assistant"
  content: string
  scope?: ChatScope
  selected_entity_keys?: string[]
  sources?: ChatSource[]
  cost?: ChatCost | null
  timestamp?: string
  model_info?: ChatModelInfo | null
  resultGraph?: ResultGraph
  provenance?: ChatProvenance | null
}

export interface ResultGraphNode {
  key: string
  name: string
  type: EntityType | string
  confidence: number
  mentioned: boolean
  relevance_reason?: string
  relevance_source?: string
  summary?: string
  properties?: Record<string, unknown>
}

export interface ResultGraphLink {
  source: string
  target: string
  type: string
  properties?: Record<string, unknown>
}

export interface ContextNode {
  key: string
  label: string
  type: EntityType
}
