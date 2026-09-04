import { fetchAPI } from "@/lib/api-client"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type CaseContextFieldType =
  | "short_text"
  | "long_text"
  | "date"
  | "number"
  | "boolean"
  | "single_choice"
  | "multiple_choice"
  | "dossier_reference"

export interface CaseContextTemplateField {
  key: string
  label: string
  type: CaseContextFieldType
  choices: string[]
  required: boolean
  position: number
}

export interface CaseContextTemplate {
  key: string
  name: string
  description?: string | null
  is_builtin: boolean
  fields: CaseContextTemplateField[]
}

export interface MandateVersion {
  id: string
  case_id: string
  version_number: number
  objective?: string | null
  key_questions: string[]
  in_scope?: string | null
  out_of_scope?: string | null
  perspective?: string | null
  success_criteria?: string | null
  constraints?: string | null
  author_user_id?: string | null
  author_name?: string | null
  created_at?: string | null
}

export interface CaseContext {
  case_id: string
  case_summary?: string | null
  background?: string | null
  investigation_type?: string | null
  jurisdiction?: string | null
  active_template_key: string
  custom_values: Record<string, unknown>
  active_mandate?: MandateVersion | null
  mandate_complete: boolean
  templates: CaseContextTemplate[]
  updated_at?: string | null
}

export type CaseContextUpdate = Pick<
  CaseContext,
  "case_summary" | "background" | "investigation_type" | "jurisdiction" | "active_template_key" | "custom_values"
>

export type MandateVersionCreate = Pick<
  MandateVersion,
  "objective" | "key_questions" | "in_scope" | "out_of_scope" | "perspective" | "success_criteria" | "constraints"
>

export type TaskStatus = "todo" | "in_progress" | "done"
export type TaskPriority = "low" | "standard" | "high" | "urgent"

export interface TaskLink {
  id?: string
  target_type: "dossier" | "entry" | "evidence"
  target_id: string
  label?: string | null
  source_anchor?: Record<string, unknown>
}

export interface InvestigationTask {
  id: string
  task_id?: string
  case_id?: string
  title: string
  description?: string | null
  status: TaskStatus
  priority: TaskPriority
  assignee_user_id?: string | null
  assignee_name?: string | null
  assignee_email?: string | null
  due_at?: string | null
  parent_task_id?: string | null
  deadline_id?: string | null
  deadline_name?: string | null
  deadline_date?: string | null
  completed_at?: string | null
  deleted_at?: string | null
  created_by_user_id?: string | null
  created_by_name?: string | null
  updated_by_user_id?: string | null
  links: TaskLink[]
  subtask_progress: { done: number; total: number }
  migration_metadata?: Record<string, unknown>
  needs_migration_review?: boolean
  created_at?: string | null
  updated_at?: string | null
  [key: string]: unknown
}

export type InvestigationTaskCreate = Pick<
  InvestigationTask,
  | "title"
  | "description"
  | "status"
  | "priority"
  | "assignee_user_id"
  | "due_at"
  | "parent_task_id"
  | "deadline_id"
  | "links"
>

export interface CaseWorkResponse {
  tasks: InvestigationTask[]
  task_total: number
  deadlines: Array<{
    id: string
    case_id: string
    name: string
    due_date: string
    created_by_user_id?: string | null
    created_at?: string | null
    updated_at?: string | null
  }>
  deadline_total: number
  bounded: boolean
  limit: number
}

export interface PinnedItem {
  id: string
  pin_id?: string
  item_type: string
  item_id: string
  evidence_file_id?: string
  filename?: string
  display_name?: string
  size?: number
  status?: string
  source_type?: string | null
  summary?: string | null
  sha256?: string
  pinned_by_user_id?: string | null
  pinned_by_name?: string | null
  created_at?: string
  [key: string]: unknown
}

export type AttentionReasonCode =
  | "deadline_overdue"
  | "deadline_due_soon"
  | "deadline_upcoming"
  | "task_overdue"
  | "task_urgent"
  | "task_due_soon"
  | "task_assigned"
  | "review_required"
  | "finding_high_significance"
  | "theory_material_change"
  | "contradiction_recorded"
  | "personal_draft"
  | "recent_casework_update"

export interface WorkspaceAttentionItem {
  attention_key: string
  source_type: string
  source_id: string
  reason_code: AttentionReasonCode
  reason_label: string
  rank: number
  priority_band: number
  title: string
  summary?: string | null
  occurred_at?: string | null
  due_at?: string | null
  href: string
  metadata: Record<string, unknown>
}

export interface WorkspaceOverviewResponse {
  case_id: string
  as_of: string
  timezone: string
  shared_attention: WorkspaceAttentionItem[]
  personal_attention: WorkspaceAttentionItem[]
  context: {
    case_summary?: string | null
    background?: string | null
    investigation_type?: string | null
    jurisdiction?: string | null
    mandate_complete: boolean
    mandate?: {
      id: string
      version_number: number
      objective?: string | null
      key_questions: string[]
      author_name?: string | null
      created_at?: string | null
    } | null
    updated_at?: string | null
  }
  recent_casework: Array<{
    id: string
    entry_type: "note" | "finding" | "theory"
    title: string
    summary?: string | null
    lifecycle_state?: string | null
    significance?: string | null
    review_state: string
    updated_at?: string | null
    href: string
  }>
  dossier_highlights: Array<{
    id: string
    display_name: string
    dossier_type: string
    summary?: string | null
    importance?: string | null
    needs_link_review: boolean
    href: string
  }>
  pinned_evidence: PinnedItem[]
  bounded: boolean
  limits: Record<string, number>
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const workspaceAPI = {
  // -- Attention-driven overview -------------------------------------------
  getOverview: (caseId: string, timezoneName: string) => {
    const qs = new URLSearchParams({ timezone: timezoneName })
    return fetchAPI<WorkspaceOverviewResponse>(
      `/api/workspace/${encodeURIComponent(caseId)}/overview?${qs}`,
    )
  },

  setAttentionState: (
    caseId: string,
    attentionKey: string,
    input: { action: "dismiss" | "snooze"; snoozed_until?: string },
  ) =>
    fetchAPI<{
      attention_key: string
      dismissed_at?: string | null
      snoozed_until?: string | null
    }>(
      `/api/workspace/${encodeURIComponent(caseId)}/attention/${encodeURIComponent(attentionKey)}`,
      { method: "PUT", body: input },
    ),

  clearAttentionState: (caseId: string, attentionKey: string) =>
    fetchAPI<void>(
      `/api/workspace/${encodeURIComponent(caseId)}/attention/${encodeURIComponent(attentionKey)}`,
      { method: "DELETE" },
    ),

  // -- Case Context (returned unwrapped) ------------------------------------
  getCaseContext: (caseId: string) =>
    fetchAPI<CaseContext>(`/api/workspace/${caseId}/context`),

  updateCaseContext: (caseId: string, context: CaseContextUpdate) =>
    fetchAPI<CaseContext>(`/api/workspace/${caseId}/context`, {
      method: "PUT",
      body: context,
    }),

  listMandateVersions: (caseId: string) =>
    fetchAPI<{ versions: MandateVersion[] }>(
      `/api/workspace/${caseId}/context/mandates`,
    ).then((result) => result.versions),

  createMandateVersion: (caseId: string, mandate: MandateVersionCreate) =>
    fetchAPI<MandateVersion>(`/api/workspace/${caseId}/context/mandates`, {
      method: "POST",
      body: mandate,
    }),

  // -- Tasks (wrapped: {"tasks": [...]}) ------------------------------------
  getTasks: (caseId: string) =>
    fetchAPI<{ tasks: InvestigationTask[]; total: number }>(
      `/api/workspace/${caseId}/tasks`,
    ).then((r) => r.tasks ?? []),

  createTask: (
    caseId: string,
    task: InvestigationTaskCreate,
  ) =>
    fetchAPI<InvestigationTask>(`/api/workspace/${caseId}/tasks`, {
      method: "POST",
      body: task,
    }),

  updateTask: (
    caseId: string,
    taskId: string,
    task: Partial<InvestigationTaskCreate>,
  ) =>
    fetchAPI<InvestigationTask>(
      `/api/workspace/${caseId}/tasks/${taskId}`,
      { method: "PATCH", body: task },
    ),

  deleteTask: (caseId: string, taskId: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/tasks/${taskId}`, {
      method: "DELETE",
    }),

  restoreTask: (caseId: string, taskId: string) =>
    fetchAPI<InvestigationTask>(
      `/api/workspace/${caseId}/tasks/${taskId}/restore`,
      { method: "POST" },
    ),

  getWork: (
    caseId: string,
    params: {
      includeTasks?: boolean
      includeDeadlines?: boolean
      taskStatus?: TaskStatus | "all"
      assigneeUserId?: string
      limit?: number
    } = {},
  ) => {
    const qs = new URLSearchParams()
    if (params.includeTasks !== undefined) qs.set("include_tasks", String(params.includeTasks))
    if (params.includeDeadlines !== undefined) qs.set("include_deadlines", String(params.includeDeadlines))
    if (params.taskStatus && params.taskStatus !== "all") qs.set("task_status", params.taskStatus)
    if (params.assigneeUserId) qs.set("assignee_user_id", params.assigneeUserId)
    if (params.limit) qs.set("limit", String(params.limit))
    const suffix = qs.toString() ? `?${qs}` : ""
    return fetchAPI<CaseWorkResponse>(`/api/workspace/${caseId}/work${suffix}`)
  },

  // -- Pinned Items (wrapped: {"pinned_items": [...]}) ----------------------
  getPinnedItems: (caseId: string) =>
    fetchAPI<{ pinned_items: PinnedItem[]; total: number }>(
      `/api/workspace/${caseId}/pinned?limit=100`,
    ).then((r) => r.pinned_items ?? []),

  getPinStatus: (caseId: string, evidenceFileIds: string[]) => {
    const qs = new URLSearchParams()
    evidenceFileIds.forEach((id) => qs.append("evidence_file_ids", id))
    return fetchAPI<{ pins: Record<string, string> }>(
      `/api/workspace/${caseId}/pinned/status?${qs}`,
    ).then((result) => result.pins)
  },

  pinItem: (
    caseId: string,
    itemType: string,
    itemId: string,
    annotationsCount?: number,
  ) => {
    const qs = new URLSearchParams({ item_type: itemType, item_id: itemId })
    if (annotationsCount !== undefined)
      qs.set("annotations_count", String(annotationsCount))
    return fetchAPI<PinnedItem>(`/api/workspace/${caseId}/pinned?${qs}`, {
      method: "POST",
    })
  },

  bulkPinItems: (caseId: string, evidenceFileIds: string[]) =>
    fetchAPI<{ pins: PinnedItem[]; created: number; already_pinned: number }>(
      `/api/workspace/${caseId}/pinned/bulk`,
      { method: "POST", body: { evidence_file_ids: evidenceFileIds } },
    ),

  unpinItem: (caseId: string, pinId: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/pinned/${pinId}`, {
      method: "DELETE",
    }),

}
