import { fetchAPI } from "@/lib/api-client"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CaseContext {
  case_id?: string
  client_profile?: Record<string, unknown>
  charges?: string[]
  allegations?: string[]
  denials?: string[]
  legal_exposure?: Record<string, unknown>
  defense_strategy?: string[]
  trial_date?: string | null
  court_info?: Record<string, unknown>
  // Legacy fields that may coexist in JSONB
  summary?: string
  objectives?: string[]
  [key: string]: unknown
}

export interface WitnessInterview {
  interview_id?: string
  date: string
  duration?: string
  statement?: string
  status?: string
  credibility_rating?: number
  risk_assessment?: string
  created_at?: string
  updated_at?: string
}

export interface Witness {
  id: string
  witness_id?: string
  name: string
  role?: string
  organization?: string
  category?: "FRIENDLY" | "NEUTRAL" | "ADVERSE"
  status?: string
  credibility_rating?: number
  statement_summary?: string
  risk_assessment?: string
  strategy_notes?: string
  interviews?: WitnessInterview[]
  created_at?: string
  updated_at?: string
  [key: string]: unknown
}

export interface InvestigativeNote {
  id: string
  note_id?: string
  title?: string
  content: string
  tags?: string[]
  created_at?: string
  updated_at?: string
  [key: string]: unknown
}

export interface Finding {
  id: string
  finding_id?: string
  title: string
  content?: string
  priority?: "HIGH" | "MEDIUM" | "LOW" | string
  linked_evidence_ids?: string[]
  linked_document_ids?: string[]
  linked_entity_keys?: string[]
  created_at?: string
  updated_at?: string
  [key: string]: unknown
}

export interface Theory {
  id: string
  theory_id?: string
  title: string
  type?: "PRIMARY" | "SECONDARY" | "NOTE"
  confidence_score?: number
  hypothesis?: string
  supporting_evidence?: string[]
  counter_arguments?: string[]
  next_steps?: string[]
  privilege_level?: "PUBLIC" | "ATTORNEY_ONLY" | "PRIVATE"
  author_id?: string
  attached_evidence_ids?: string[]
  attached_witness_ids?: string[]
  attached_note_ids?: string[]
  attached_document_ids?: string[]
  attached_task_ids?: string[]
  attached_graph_data?: {
    entity_keys: string[]
    entities: Array<{
      key: string
      name: string
      type: string
      summary?: string
      distance: number
    }>
    created_at: string
  }
  created_at?: string
  updated_at?: string
  [key: string]: unknown
}

export interface InvestigationTask {
  id: string
  task_id?: string
  title: string
  description?: string
  priority?: "URGENT" | "HIGH" | "STANDARD"
  due_date?: string
  assigned_to?: string
  status?: "PENDING" | "IN_PROGRESS" | "COMPLETED" | string
  completion_percentage?: number
  status_text?: string
  created_at?: string
  updated_at?: string
  [key: string]: unknown
}

export interface DeadlineConfig {
  trial_date?: string | null
  trial_court?: string | null
  judge?: string | null
  court_division?: string | null
  deadlines?: Array<{
    title: string
    date: string
    type?: string
    notes?: string
  }>
  [key: string]: unknown
}

export interface PinnedItem {
  id: string
  pin_id?: string
  item_type: string
  item_id: string
  user_id?: string
  annotations_count?: number
  created_at?: string
  [key: string]: unknown
}

export interface PresenceEntry {
  user_id: string
  user_name: string
  status: string
  last_seen?: string
}

export interface TheoryGraphResult {
  entity_keys: string[]
  entities: Array<{
    key: string
    name: string
    type: string
    summary?: string
    distance: number
  }>
  text_length?: number
}

export interface TimelineEvent {
  id: string
  type: string
  thread: string
  date: string
  title: string
  description?: string
  metadata?: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Normalize backend ID field (e.g. theory_id) to `id` */
function withId<T extends Record<string, unknown>>(
  item: T,
  field: string,
): T & { id: string } {
  return { ...item, id: (item[field] as string) ?? (item.id as string) }
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const workspaceAPI = {
  // -- Case Context (returned unwrapped) ------------------------------------
  getCaseContext: (caseId: string) =>
    fetchAPI<CaseContext>(`/api/workspace/${caseId}/context`),

  updateCaseContext: (caseId: string, context: Partial<CaseContext>) =>
    fetchAPI<CaseContext>(`/api/workspace/${caseId}/context`, {
      method: "PUT",
      body: context,
    }),

  // -- Witnesses (wrapped: {"witnesses": [...]}) ----------------------------
  getWitnesses: (caseId: string) =>
    fetchAPI<{ witnesses: Witness[] }>(
      `/api/workspace/${caseId}/witnesses`,
    ).then((r) => (r.witnesses ?? []).map((w) => withId(w, "witness_id"))),

  createWitness: (caseId: string, witness: Omit<Witness, "id">) =>
    fetchAPI<Witness>(`/api/workspace/${caseId}/witnesses`, {
      method: "POST",
      body: witness,
    }).then((w) => withId(w, "witness_id")),

  updateWitness: (
    caseId: string,
    witnessId: string,
    witness: Partial<Witness>,
  ) =>
    fetchAPI<Witness>(
      `/api/workspace/${caseId}/witnesses/${witnessId}`,
      { method: "PUT", body: witness },
    ).then((w) => withId(w, "witness_id")),

  deleteWitness: (caseId: string, witnessId: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/witnesses/${witnessId}`, {
      method: "DELETE",
    }),

  // -- Investigative Notes (wrapped: {"notes": [...]}) ----------------------
  getNotes: (caseId: string) =>
    fetchAPI<{ notes: InvestigativeNote[] }>(
      `/api/workspace/${caseId}/notes`,
    ).then((r) => (r.notes ?? []).map((n) => withId(n, "note_id"))),

  createNote: (
    caseId: string,
    note: Omit<InvestigativeNote, "id">,
  ) =>
    fetchAPI<InvestigativeNote>(`/api/workspace/${caseId}/notes`, {
      method: "POST",
      body: note,
    }).then((n) => withId(n, "note_id")),

  updateNote: (
    caseId: string,
    noteId: string,
    note: Partial<InvestigativeNote>,
  ) =>
    fetchAPI<InvestigativeNote>(
      `/api/workspace/${caseId}/notes/${noteId}`,
      { method: "PUT", body: note },
    ).then((n) => withId(n, "note_id")),

  deleteNote: (caseId: string, noteId: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/notes/${noteId}`, {
      method: "DELETE",
    }),

  // -- Findings (wrapped: {"findings": [...]}) -----------------------------
  getFindings: (caseId: string) =>
    fetchAPI<{ findings: Finding[] }>(
      `/api/workspace/${caseId}/findings`,
    ).then((r) => (r.findings ?? []).map((f) => withId(f, "finding_id"))),

  createFinding: (caseId: string, finding: Omit<Finding, "id">) =>
    fetchAPI<Finding>(`/api/workspace/${caseId}/findings`, {
      method: "POST",
      body: finding,
    }).then((f) => withId(f, "finding_id")),

  updateFinding: (
    caseId: string,
    findingId: string,
    finding: Partial<Finding>,
  ) =>
    fetchAPI<Finding>(`/api/workspace/${caseId}/findings/${findingId}`, {
      method: "PUT",
      body: finding,
    }).then((f) => withId(f, "finding_id")),

  deleteFinding: (caseId: string, findingId: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/findings/${findingId}`, {
      method: "DELETE",
    }),

  // -- Theories (wrapped: {"theories": [...]}) ------------------------------
  getTheories: (caseId: string) =>
    fetchAPI<{ theories: Theory[] }>(
      `/api/workspace/${caseId}/theories`,
    ).then((r) => (r.theories ?? []).map((t) => withId(t, "theory_id"))),

  createTheory: (caseId: string, theory: Omit<Theory, "id">) =>
    fetchAPI<Theory>(`/api/workspace/${caseId}/theories`, {
      method: "POST",
      body: theory,
    }).then((t) => withId(t, "theory_id")),

  updateTheory: (
    caseId: string,
    theoryId: string,
    theory: Partial<Theory>,
  ) =>
    fetchAPI<Theory>(
      `/api/workspace/${caseId}/theories/${theoryId}`,
      { method: "PUT", body: theory },
    ).then((t) => withId(t, "theory_id")),

  deleteTheory: (caseId: string, theoryId: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/theories/${theoryId}`, {
      method: "DELETE",
    }),

  buildTheoryGraph: (
    caseId: string,
    theoryId: string,
    options?: Record<string, unknown>,
  ) =>
    fetchAPI<TheoryGraphResult>(
      `/api/workspace/${caseId}/theories/${theoryId}/build-graph`,
      { method: "POST", body: options },
    ),

  buildWorkspaceGraph: (
    caseId: string,
    request: {
      source_type: "theory" | "witness" | "note"
      source_id: string
      include_attached_items?: boolean
      top_k?: number
    },
  ) =>
    fetchAPI<TheoryGraphResult>(`/api/workspace/${caseId}/build-graph`, {
      method: "POST",
      body: request,
    }),

  // -- Tasks (wrapped: {"tasks": [...]}) ------------------------------------
  getTasks: (caseId: string) =>
    fetchAPI<{ tasks: InvestigationTask[] }>(
      `/api/workspace/${caseId}/tasks`,
    ).then((r) => (r.tasks ?? []).map((t) => withId(t, "task_id"))),

  createTask: (
    caseId: string,
    task: Omit<InvestigationTask, "id">,
  ) =>
    fetchAPI<InvestigationTask>(`/api/workspace/${caseId}/tasks`, {
      method: "POST",
      body: task,
    }).then((t) => withId(t, "task_id")),

  updateTask: (
    caseId: string,
    taskId: string,
    task: Partial<InvestigationTask>,
  ) =>
    fetchAPI<InvestigationTask>(
      `/api/workspace/${caseId}/tasks/${taskId}`,
      { method: "PUT", body: task },
    ).then((t) => withId(t, "task_id")),

  deleteTask: (caseId: string, taskId: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/tasks/${taskId}`, {
      method: "DELETE",
    }),

  // -- Deadlines (returned unwrapped) ---------------------------------------
  getDeadlines: (caseId: string) =>
    fetchAPI<DeadlineConfig>(`/api/workspace/${caseId}/deadlines`),

  updateDeadlines: (caseId: string, deadlineConfig: DeadlineConfig) =>
    fetchAPI<DeadlineConfig>(`/api/workspace/${caseId}/deadlines`, {
      method: "PUT",
      body: deadlineConfig,
    }),

  // -- Pinned Items (wrapped: {"pinned_items": [...]}) ----------------------
  getPinnedItems: (caseId: string) =>
    fetchAPI<{ pinned_items: PinnedItem[] }>(
      `/api/workspace/${caseId}/pinned`,
    ).then((r) => (r.pinned_items ?? []).map((p) => withId(p, "pin_id"))),

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
    }).then((p) => withId(p, "pin_id"))
  },

  unpinItem: (caseId: string, pinId: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/pinned/${pinId}`, {
      method: "DELETE",
    }),

  // -- Presence (wrapped: {"online_users": [], "count": N}) -----------------
  getPresence: (caseId: string) =>
    fetchAPI<{ online_users: PresenceEntry[]; count: number }>(
      `/api/workspace/${caseId}/presence`,
    ).then((r) => r.online_users ?? []),

  updatePresence: (caseId: string, status: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/presence`, {
      method: "PUT",
      body: { status },
    }),

  // -- Investigation Timeline (wrapped: {"events": [], "total": N}) ---------
  getInvestigationTimeline: (caseId: string) =>
    fetchAPI<{ events: TimelineEvent[]; total: number }>(
      `/api/workspace/${caseId}/investigation-timeline`,
    ).then((r) => r.events ?? []),

  getTheoryTimeline: (caseId: string, theoryId: string) =>
    fetchAPI<{ events: TimelineEvent[]; total: number }>(
      `/api/workspace/${caseId}/theories/${theoryId}/timeline`,
    ).then((r) => r.events ?? []),
}
