import { fetchAPI } from "@/lib/api-client"

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
