import { fetchAPI } from "@/lib/api-client"
import type {
  Conversation,
  CreateChatHistory,
  ChatMessageData,
  ResultGraph,
} from "./types"

// ─── Chat Request/Response ───────────────────────────────────
interface ChatRequest {
  question: string
  selected_keys?: string[]
  model?: string
  provider?: string
  confidence_threshold?: number
  case_id: string
}

interface ChatResponse {
  answer: string
  sources: { filename: string; excerpt?: string }[]
  cost?: number
  model_info?: { provider: string; model: string }
  result_graph?: ResultGraph
}

interface ChatSuggestion {
  question: string
}

const CHAT_DEFAULTS = {
  provider: "openai",
  model: "gpt-4o",
} as const

export const chatAPI = {
  ask: (params: ChatRequest) =>
    fetchAPI<ChatResponse>("/api/chat", {
      method: "POST",
      body: {
        provider: CHAT_DEFAULTS.provider,
        model: CHAT_DEFAULTS.model,
        ...params,
      },
      timeout: 120000,
    }),

  getSuggestions: (caseId: string, selectedKeys?: string[]) =>
    fetchAPI<ChatSuggestion[]>("/api/chat/suggestions", {
      method: "POST",
      body: { case_id: caseId, selected_keys: selectedKeys },
    }),
}

// ─── Chat History API ────────────────────────────────────────
interface ChatHistoryResponse {
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

function toConversation(r: ChatHistoryResponse): Conversation {
  return {
    id: r.id,
    name: r.name,
    messages: r.messages,
    timestamp: r.timestamp,
    created_at: r.created_at,
    owner: r.owner,
    snapshot_id: r.snapshot_id,
    case_id: r.case_id,
    case_version: r.case_version,
    message_count: r.message_count,
  }
}

export const chatHistoryAPI = {
  list: () =>
    fetchAPI<ChatHistoryResponse[]>("/api/chat-history").then((res) =>
      res.map(toConversation)
    ),

  get: (chatId: string) =>
    fetchAPI<ChatHistoryResponse>(`/api/chat-history/${chatId}`).then(
      toConversation
    ),

  create: (data: CreateChatHistory) =>
    fetchAPI<ChatHistoryResponse>("/api/chat-history", {
      method: "POST",
      body: data,
    }).then(toConversation),

  update: (chatId: string, data: Partial<CreateChatHistory>) =>
    fetchAPI<ChatHistoryResponse>(`/api/chat-history/${chatId}`, {
      method: "PUT",
      body: data,
    }).then(toConversation),

  delete: (chatId: string) =>
    fetchAPI<{ status: string; id: string }>(
      `/api/chat-history/${chatId}`,
      { method: "DELETE" }
    ),
}

export type { ChatRequest, ChatResponse, ChatSuggestion }
