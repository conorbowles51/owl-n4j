export type AgentArtifactType =
  | "graph"
  | "table"
  | "map"
  | "report"
  | "chart"

export interface AgentArtifact {
  id: string
  type: AgentArtifactType
  title: string
  data: Record<string, unknown>
  metadata: Record<string, unknown>
}

export interface AgentToolTraceItem {
  id: string
  name: string
  arguments: Record<string, unknown>
  status: "success" | "error"
  duration_ms: number
  summary?: string | null
  result_id?: string | null
  error?: string | null
  activity?: AgentActivityItem | null
}

export interface AgentActivityItem {
  id: string
  tool_name?: string | null
  phase?: "plan" | "result" | string
  status?: "running" | "success" | "error" | string
  title: string
  detail?: string | null
  result_detail?: string | null
  duration_ms?: number | null
}

export interface AgentClarificationOption {
  id: string
  label: string
  description?: string | null
}

export interface AgentClarification {
  question: string
  options: AgentClarificationOption[]
  allow_free_text: boolean
  pending_run_id: string
  thread_id: string
  original_message: string
  context: Record<string, unknown>
}

export interface AgentCost {
  usd: number
  prompt_tokens?: number | null
  completion_tokens?: number | null
  total_tokens?: number | null
  cost_record_id?: string | null
}

export interface AgentModelInfo {
  provider: string
  model_id: string
  model_name: string
  server: string
}

export interface AgentMessageResponse {
  thread_id: string
  run_id: string
  user_message_id?: string | null
  assistant_message_id?: string | null
  answer: string
  artifacts: AgentArtifact[]
  tool_trace: AgentToolTraceItem[]
  model_info: AgentModelInfo
  cost?: AgentCost | null
  clarification?: AgentClarification | null
  status: "running" | "completed" | "failed" | "cancelled" | "clarification_required"
  created_at: string
}

export type AgentStreamEvent =
  | {
      type: "run_started"
      thread_id: string
      run_id: string
      user_message_id: string
      model_info: AgentModelInfo
    }
  | {
      type: "status"
      stage?: string
      message: string
    }
  | {
      type: "activity"
      activity: AgentActivityItem
    }
  | {
      type: "tool_plan"
      tools: Array<{
        id?: string | null
        name?: string | null
        arguments?: Record<string, unknown>
      }>
    }
  | {
      type: "tool_result"
      tool: AgentToolTraceItem
    }
  | {
      type: "artifact"
      artifact: AgentArtifact
    }
  | {
      type: "clarification"
      clarification: AgentClarification
    }
  | {
      type: "assistant_draft"
      answer: string
    }
  | {
      type: "answer"
      answer: string
    }
  | {
      type: "done"
      response: AgentMessageResponse
    }
  | {
      type: "cancelled"
      run_id: string
      thread_id: string
      message: string
    }
  | {
      type: "error"
      run_id?: string
      thread_id?: string
      message: string
    }

export interface AgentRunStatus {
  run_id: string
  thread_id: string
  status: "running" | "completed" | "failed" | "cancelled" | "clarification_required"
  error?: string | null
  completed_at?: string | null
}

export interface AgentThreadSummary {
  id: string
  case_id: string
  title: string
  status: string
  owner_user_id: string
  message_count: number
  last_message_at: string
  created_at: string
  updated_at: string
}

export interface AgentStoredMessage {
  id: string
  role: "user" | "assistant" | string
  content: string
  run_id?: string | null
  model_provider?: string | null
  model_id?: string | null
  artifact_ids: string[]
  tool_trace_summary: Array<Record<string, unknown>>
  clarification?: AgentClarification | null
  created_at: string
}

export interface AgentThreadDetail extends AgentThreadSummary {
  messages: AgentStoredMessage[]
  artifacts: AgentArtifact[]
}

export interface AgentClientMessage {
  id: string
  role: "user" | "assistant"
  content: string
  clarification?: AgentClarification | null
  toolTraceSummary?: AgentToolTraceItem[]
  pending?: boolean
  createdAt?: string
}
