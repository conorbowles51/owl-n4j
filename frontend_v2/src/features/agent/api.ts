import { fetchAPI } from "@/lib/api-client"
import type {
  AgentMessageResponse,
  AgentRunStatus,
  AgentStreamEvent,
  AgentThreadDetail,
  AgentThreadSummary,
  AgentWorkflowCatalogue,
} from "./types"
import type { CaseLayer } from "@/features/significant/types"

export type AgentArtifactExportFormat = "csv" | "pdf" | "docx"

export interface SendAgentMessageParams {
  caseId: string
  message: string
  threadId?: string | null
  artifactPreference?: "auto" | "none" | "graph" | "table" | "map" | "report" | "chart"
  provider?: string
  model?: string
  caseLayer?: CaseLayer
  mandateOverride?: Record<string, unknown>
  workflowId?: string
  /** All-cases mode: off unless the person switches it on; off again for each new conversation. */
  allCases?: boolean
}

export const agentAPI = {
  listThreads: (caseId: string) =>
    fetchAPI<AgentThreadSummary[]>(`/api/agent/threads?case_id=${caseId}`),

  listWorkflows: (caseId: string) =>
    fetchAPI<AgentWorkflowCatalogue>(`/api/agent/workflows?case_id=${encodeURIComponent(caseId)}`),

  getThread: (threadId: string) =>
    fetchAPI<AgentThreadDetail>(`/api/agent/threads/${threadId}`),

  sendMessage: (params: SendAgentMessageParams) =>
    fetchAPI<AgentMessageResponse>("/api/agent/messages", {
      method: "POST",
      body: {
        case_id: params.caseId,
        thread_id: params.threadId || undefined,
        message: params.message,
        ...(params.provider ? { provider: params.provider } : {}),
        ...(params.model ? { model: params.model } : {}),
        artifact_preference: params.artifactPreference || "auto",
        case_layer: params.caseLayer || "all",
        persist: true,
        mandate_override: params.mandateOverride,
        ...(params.workflowId ? { workflow_id: params.workflowId } : {}),
        ...(params.allCases ? { all_cases: true } : {}),
      },
      timeout: 240000,
    }),

  streamMessage: async (
    params: SendAgentMessageParams,
    onEvent: (event: AgentStreamEvent) => void
  ) => {
    const response = await fetch("/api/agent/messages/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        case_id: params.caseId,
        thread_id: params.threadId || undefined,
        message: params.message,
        ...(params.provider ? { provider: params.provider } : {}),
        ...(params.model ? { model: params.model } : {}),
        artifact_preference: params.artifactPreference || "auto",
        case_layer: params.caseLayer || "all",
        persist: true,
        mandate_override: params.mandateOverride,
        ...(params.workflowId ? { workflow_id: params.workflowId } : {}),
        ...(params.allCases ? { all_cases: true } : {}),
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

  adoptCurrentMandate: (threadId: string) =>
    fetchAPI<import("./types").AgentMandateUsage>(
      `/api/agent/threads/${threadId}/adopt-current-mandate`,
      { method: "POST" },
    ),

  /** CO-18: a person accepts an answer into a dossier assessment (stored AI-assisted, its model named). */
  acceptIntoAssessment: (caseId: string, messageId: string, dossierId: string, category: string) =>
    fetchAPI<{
      id: string
      read_by: string | null
      cited_records: { cited: number; linked: number; not_in_case: number; over_limit: number; sentence: string | null }
    }>(`/api/agent/messages/${encodeURIComponent(messageId)}/accept-into-assessment`, {
      method: "POST",
      body: { case_id: caseId, dossier_id: dossierId, category },
    }),

  getRunRecord: (runId: string) =>
    fetchAPI<import("./types").AgentRunRecord>(`/api/agent/runs/${encodeURIComponent(runId)}/record`),

  runRecordExportUrl: (runId: string, kind: "strategy" | "not_examined", format: "csv" | "pdf") =>
    `/api/agent/runs/${encodeURIComponent(runId)}/record/export?kind=${kind}&format=${format}`,

  artifactExportUrl: (artifactId: string, format: AgentArtifactExportFormat = "csv") =>
    `/api/agent/artifacts/${artifactId}/export?format=${format}`,
}
