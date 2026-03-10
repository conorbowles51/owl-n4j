import type { EntityType } from "@/lib/theme"

// ─── Conversation ────────────────────────────────────────────
export interface ConversationSummary {
  id: string
  title: string
  messageCount: number
  lastMessageAt: string
  caseId?: string
}

export interface Conversation {
  id: string
  name: string
  messages: ChatMessageData[]
  timestamp: string
  created_at: string
  owner: string
  snapshot_id?: string
  case_id?: string
  case_version?: number
  message_count: number
}

export interface CreateChatHistory {
  name?: string
  messages: ChatMessageData[]
  case_id?: string
}

// ─── Messages ────────────────────────────────────────────────
export interface ChatMessageData {
  role: "user" | "assistant"
  content: string
  sources?: { filename: string; excerpt?: string }[]
  cost?: number
  timestamp?: string
  model_info?: { provider: string; model: string }
  resultGraph?: ResultGraph
}

// ─── Result Graph ────────────────────────────────────────────
export interface ResultGraph {
  nodes: ResultGraphNode[]
  links: ResultGraphLink[]
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

// ─── Context ─────────────────────────────────────────────────
export interface ContextNode {
  key: string
  label: string
  type: EntityType
}
