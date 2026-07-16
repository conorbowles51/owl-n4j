import { fetchAPI } from "@/lib/api-client"
import type {
  AgentArtifact,
  AgentMessageResponse,
  AgentRunStatus,
  AgentStreamEvent,
  AgentThreadDetail,
  AgentThreadSummary,
} from "./types"

export type AgentArtifactExportFormat = "csv" | "pdf" | "docx"

export interface SendAgentMessageParams {
  caseId: string
  message: string
  threadId?: string | null
  artifactPreference?: "auto" | "none" | "graph" | "table" | "map" | "report" | "chart"
  provider?: string
  model?: string
}

const AGENT_DEFAULTS = {
  provider: "openai",
  model: "gpt-5-mini",
} as const

export const agentAPI = {
  listThreads: (caseId: string) =>
    fetchAPI<AgentThreadSummary[]>(`/api/agent/threads?case_id=${caseId}`),

  getThread: (threadId: string) =>
    fetchAPI<AgentThreadDetail>(`/api/agent/threads/${threadId}`),

  sendMessage: (params: SendAgentMessageParams) =>
    fetchAPI<AgentMessageResponse>("/api/agent/messages", {
      method: "POST",
      body: {
        case_id: params.caseId,
        thread_id: params.threadId || undefined,
        message: params.message,
        provider: params.provider || AGENT_DEFAULTS.provider,
        model: params.model || AGENT_DEFAULTS.model,
        artifact_preference: params.artifactPreference || "auto",
        persist: true,
      },
      timeout: 240000,
    }),

  streamMessage: async (
    params: SendAgentMessageParams,
    onEvent: (event: AgentStreamEvent) => void
  ) => {
    const token = localStorage.getItem("authToken")
    const response = await fetch("/api/agent/messages/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      credentials: "include",
      body: JSON.stringify({
        case_id: params.caseId,
        thread_id: params.threadId || undefined,
        message: params.message,
        provider: params.provider || AGENT_DEFAULTS.provider,
        model: params.model || AGENT_DEFAULTS.model,
        artifact_preference: params.artifactPreference || "auto",
        persist: true,
      }),
    })

    if (!response.ok) {
      let message = `Request failed: ${response.status}`
      try {
        const error = await response.json()
        if (typeof error?.detail === "string") message = error.detail
      } catch {
        // keep fallback
      }
      throw new Error(message)
    }
    if (!response.body) {
      throw new Error("Agent stream did not return a response body")
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split("\n\n")
      buffer = chunks.pop() ?? ""

      for (const chunk of chunks) {
        const dataLine = chunk
          .split("\n")
          .find((line) => line.startsWith("data: "))
        if (!dataLine) continue
        const raw = dataLine.slice("data: ".length)
        if (!raw.trim()) continue
        onEvent(JSON.parse(raw) as AgentStreamEvent)
      }
    }

    if (buffer.trim().startsWith("data: ")) {
      onEvent(JSON.parse(buffer.trim().slice("data: ".length)) as AgentStreamEvent)
    }
  },

  cancelRun: (runId: string) =>
    fetchAPI<AgentRunStatus>(`/api/agent/runs/${runId}:cancel`, {
      method: "POST",
    }),

  approveArtifact: (artifactId: string) =>
    fetchAPI<AgentArtifact>(`/api/agent/artifacts/${artifactId}:approve`, {
      method: "POST",
    }),

  revertArtifact: (artifactId: string) =>
    fetchAPI<AgentArtifact>(`/api/agent/artifacts/${artifactId}:revert`, {
      method: "POST",
    }),

  artifactExportUrl: (artifactId: string, format: AgentArtifactExportFormat = "csv") =>
    `/api/agent/artifacts/${artifactId}/export?format=${format}`,
}
