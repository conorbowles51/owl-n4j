import { fetchAPI } from "@/lib/api-client"
import type {
  ChatCost,
  ChatModelInfo,
  ChatProvenance,
  ChatScope,
  Conversation,
  CreateChatHistory,
  ChatMessageData,
  ResultGraph,
} from "./types"

export interface ChatRequest {
  question: string
  case_id: string
  conversation_id?: string
  scope: ChatScope
  selected_entity_keys?: string[]
  model?: string
  provider?: string
  confidence_threshold?: number
  persist?: boolean
}

export interface ChatSuggestion {
  question: string
}

export interface ChatResponse {
  conversation_id?: string | null
  message_id: string
  answer: string
  sources: { filename: string; excerpt?: string; page?: number }[]
  cost?: ChatCost | null
  model_info: ChatModelInfo
  result_graph?: ResultGraph
  provenance: ChatProvenance
  suggestions: ChatSuggestion[]
}

interface ChatSuggestionsResponse {
  suggestions: ChatSuggestion[]
}

const CHAT_DEFAULTS = {
  provider: "openai",
  model: "gpt-5-mini",
} as const

export const chatAPI = {
  ask: (params: ChatRequest) =>
    fetchAPI<ChatResponse>("/api/chat", {
      method: "POST",
      body: {
        provider: CHAT_DEFAULTS.provider,
        model: CHAT_DEFAULTS.model,
        persist: false,
        ...params,
      },
      timeout: 120000,
    }),

  getSuggestions: (caseId: string, selectedEntityKeys?: string[]) =>
    fetchAPI<ChatSuggestionsResponse>("/api/chat/suggestions", {
      method: "POST",
      body: { case_id: caseId, selected_entity_keys: selectedEntityKeys },
    }).then((res) => res.suggestions),
}

interface ChatHistoryResponse {
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

interface ChatHistorySummaryResponse {
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

function toConversation(r: ChatHistoryResponse): Conversation {
  return {
    id: r.id,
    name: r.name,
    messages: r.messages,
    timestamp: r.timestamp,
    created_at: r.created_at,
    updated_at: r.updated_at,
    last_message_at: r.last_message_at,
    owner: r.owner,
    owner_user_id: r.owner_user_id,
    snapshot_id: r.snapshot_id,
    case_id: r.case_id,
    case_revision_id: r.case_revision_id,
    message_count: r.message_count,
  }
}

export const chatHistoryAPI = {
  list: (caseId?: string) => {
    const qs = caseId ? `?case_id=${encodeURIComponent(caseId)}` : ""
    return fetchAPI<ChatHistorySummaryResponse[]>(
      `/api/chat-history${qs}`
    ).then((res) =>
      res.map((item) => ({
        id: item.id,
        name: item.name,
        messages: [],
        timestamp: item.timestamp,
        created_at: item.created_at,
        updated_at: item.updated_at,
        last_message_at: item.last_message_at,
        owner_user_id: item.owner_user_id,
        case_id: item.case_id,
        message_count: item.message_count,
      }))
    )
  },

  get: (chatId: string) =>
    fetchAPI<ChatHistoryResponse>(`/api/chat-history/${chatId}`).then(
      toConversation
    ),

  create: (data: CreateChatHistory) =>
    fetchAPI<ChatHistoryResponse>("/api/chat-history", {
      method: "POST",
      body: data,
    }).then(toConversation),

  update: (
    chatId: string,
    data: Partial<Pick<CreateChatHistory, "name" | "messages">>
  ) =>
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
