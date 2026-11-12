export type AgentArtifactType =
  | "graph"
  | "table"
  | "map"
  | "report"
  | "chart"
  | "workbook"
  | "presentation"
  | "interactive"
  | "timeline"
  | "matrix"
  | "diagram"

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
  reasoning?: string | null
  written_by?: string | null
}

/** Every citation of an answer checked against the case (backend services/case_citations.check_text). */
export interface AgentCitationCheck {
  available?: boolean
  reason?: string
  total?: number
  ok?: number
  not_in_case?: number
  ambiguous?: number
  other_case?: number
  page_not_given?: number
  by_scheme?: Record<string, number>
  problems?: Array<{ href: string; scheme: string; status: string; reason?: string }>
}

export interface AgentMessageResponse {
  thread_id: string
  run_id: string
  user_message_id?: string | null
  assistant_message_id?: string | null
  answer: string
  citation_check?: AgentCitationCheck | null
  artifacts: AgentArtifact[]
  tool_trace: AgentToolTraceItem[]
  model_info: AgentModelInfo
  cost?: AgentCost | null
  clarification?: AgentClarification | null
  status: "running" | "completed" | "failed" | "cancelled" | "clarification_required" | "interrupted" | "needs_revision"
  created_at: string
  mandate: AgentMandateUsage
}

export interface AgentMandateUsage {
  version?: { id: string; version_number: number; objective?: string | null } | null
  active_version_id?: string | null
  active_version_number?: number | null
  is_stale: boolean
  is_incomplete: boolean
  temporary_override?: boolean
}

export type AgentStreamEvent =
  | {
      type: "run_started"
      thread_id: string
      run_id: string
      user_message_id: string
      model_info: AgentModelInfo
      started_at?: string
      server_time?: string
      progress?: import("./stores/agent-run.store").AgentRunProgress
    }
  | {
      type: "progress"
      run_id?: string | null
      progress: import("./stores/agent-run.store").AgentRunProgress
      elapsed_seconds?: number
      server_time?: string
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
      type: "steering"
      entries: AgentSteeringEntry[]
      applied: AgentSteeringEntry[]
      off: string[]
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
  status: "running" | "completed" | "failed" | "cancelled" | "clarification_required" | "interrupted" | "needs_revision"
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
  mandate_version_id?: string | null
}

export interface AgentStoredMessage {
  id: string
  role: "user" | "assistant" | string
  content: string
  run_id?: string | null
  model_provider?: string | null
  model_id?: string | null
  /** "Written by DeepSeek V4 Pro · thinks longer" (the model that wrote the answer). */
  written_by?: string | null
  artifact_ids: string[]
  tool_trace_summary: Array<Record<string, unknown>>
  citation_check?: AgentCitationCheck | null
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
  citationCheck?: AgentCitationCheck | null
  pending?: boolean
  createdAt?: string
  /** The run that produced this answer (its run record opens from the answer). */
  runId?: string | null
  /** The model that wrote this answer, shown on it. */
  writtenBy?: string | null
  /** A failed run's question: the failure offers Retry. */
  retryQuestion?: string | null
}

export interface AgentModelChoice {
  key: string
  provider: string
  model_id: string
  model_name: string
  reasoning: "off" | "high" | "max"
  label: string
  default: boolean
}

export interface AgentModelChoices {
  default: string
  choices: AgentModelChoice[]
}

/** The disclosure record of one agent run (GET /api/agent/runs/{id}/record). */
export interface AgentRunRecord {
  run_id: string
  status: string
  for_user: { id: string | null; name: string | null; email: string | null }
  started_at: string | null
  completed_at: string | null
  provider: string
  model_id: string
  prompt_version: string | null
  prompt_version_label: string | null
  tool_budget: number | null
  tool_calls_used: number
  unrun_tool_calls: { name: string | null }[]
  case_layer: string
  /** All-cases mode was on for this run (the person switched it on). */
  all_cases?: boolean
  /** This run's case, then every other case it read. */
  cases_read?: { case_id: string; case_name: string | null; this_case: boolean }[]
  summary: {
    items_returned?: number
    items_shown?: number
    items_opened?: number
    items_cited?: number
    items_in_artifact?: number
    items_not_examined?: number
    model_not_shown?: number
    tool_not_returned?: number
    basis?: string
  }
  calls: { sequence: number; name: string; total: number | null; returned: number | null }[]
  not_deterministic: string
}

/** A guided investigative workflow (backend services/agent/workflows.py) and its readiness on one case. */
export interface AgentWorkflowReadiness {
  id: string
  number: number
  title: string
  status: "ready" | "partial" | "not_possible" | "unknown"
  reasons: string[]
  tools_missing: string[]
  steps_that_run: number
  steps: {
    tool: string
    why: string
    optional: boolean
    by_person: boolean
    in_build: boolean
    data_missing: string[]
    runs: boolean
  }[]
}

export interface AgentWorkflow {
  id: string
  number: number
  title: string
  question: string
  starting_question: string
  extra: boolean
  steps: string[]
  proposals: string[]
  person_confirms: string
  adds_requirement: string | null
  requirement_met_by: string[]
  readiness?: AgentWorkflowReadiness
}

export interface AgentWorkflowCatalogue {
  schema: string
  counts: Record<string, number> | null
  workflows: AgentWorkflow[]
  total: number
}

/** A run still working in the case (GET /api/agent/runs/active), or one run's live state (GET /api/agent/runs/{id}). */
export interface AgentLiveRun {
  run_id: string
  thread_id: string
  status?: AgentRunStatus["status"]
  input_message?: string | null
  started_at?: string | null
  progress?: import("./stores/agent-run.store").AgentRunProgress | null
  heartbeat_at?: string | null
  stale?: boolean
  server_time?: string | null
  error?: string | null
  steering?: AgentRunSteering | null
  tool_trace?: AgentToolTraceItem[]
}

/** One switch or note the person sent while a run worked (backend services/agent/tool_groups.py trail_entry). */
export interface AgentSteeringEntry {
  id: string
  kind: "switch" | "note"
  group?: string | null
  on?: boolean | null
  note?: string | null
  title: string
  result: string
  /** The last finished step when the run took it; it applies from applies_from. Absent while not yet taken. */
  step?: number | null
  applies_from?: number | null
  at?: string | null
}

/** A run's tool switches: groups chosen from the question, entries taken (with their step), entries not yet taken,
 * and the groups off now. */
export interface AgentRunSteering {
  chosen: string[]
  applied: AgentSteeringEntry[]
  pending: AgentSteeringEntry[]
  off: string[]
}

/** A tool group as the run card lists it (GET /api/agent/tool-groups). */
export interface AgentToolGroup {
  id: string
  name: string
  about: string
  tools: string[]
  switchable: boolean
}

/** What the agent can work with (GET /api/agent/capabilities): plain labels, descriptions and example questions. */
export interface AgentCapabilityType {
  id: string
  label: string
  description: string
  examples: string[]
}

export interface AgentCapabilities {
  schema: string
  types: AgentCapabilityType[]
  total: number
  note: string
  actions?: { id: string; label: string; mode: string; description: string }[]
  scope?: string
  review?: string
  unavailable_actions?: string[]
}
