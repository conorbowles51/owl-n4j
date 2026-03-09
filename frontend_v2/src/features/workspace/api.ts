import { fetchAPI } from "@/lib/api-client"

export interface CaseContext {
  summary?: string
  objectives?: string[]
  key_questions?: string[]
  [key: string]: unknown
}

export interface Witness {
  id: string
  name: string
  role?: string
  status?: string
  notes?: string
  [key: string]: unknown
}

export interface InvestigativeNote {
  id: string
  title: string
  content: string
  created_at?: string
  updated_at?: string
  [key: string]: unknown
}

export interface Theory {
  id: string
  title: string
  description?: string
  status?: string
  evidence_for?: string[]
  evidence_against?: string[]
  [key: string]: unknown
}

export interface InvestigationTask {
  id: string
  title: string
  status?: string
  priority?: string
  assignee?: string
  due_date?: string
  [key: string]: unknown
}

export interface DeadlineConfig {
  [key: string]: unknown
}

export interface PinnedItem {
  id: string
  item_type: string
  item_id: string
  annotations_count?: number
  [key: string]: unknown
}

export interface PresenceEntry {
  user_id: string
  user_name: string
  status: string
  last_seen?: string
}

export const workspaceAPI = {
  // Case Context
  getCaseContext: (caseId: string) =>
    fetchAPI<CaseContext>(`/api/workspace/${caseId}/context`),

  updateCaseContext: (caseId: string, context: CaseContext) =>
    fetchAPI<CaseContext>(`/api/workspace/${caseId}/context`, {
      method: "PUT",
      body: context,
    }),

  // Witnesses
  getWitnesses: (caseId: string) =>
    fetchAPI<Witness[]>(`/api/workspace/${caseId}/witnesses`),

  createWitness: (caseId: string, witness: Omit<Witness, "id">) =>
    fetchAPI<Witness>(`/api/workspace/${caseId}/witnesses`, {
      method: "POST",
      body: witness,
    }),

  updateWitness: (caseId: string, witnessId: string, witness: Partial<Witness>) =>
    fetchAPI<Witness>(`/api/workspace/${caseId}/witnesses/${witnessId}`, {
      method: "PUT",
      body: witness,
    }),

  deleteWitness: (caseId: string, witnessId: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/witnesses/${witnessId}`, {
      method: "DELETE",
    }),

  // Investigative Notes
  getNotes: (caseId: string) =>
    fetchAPI<InvestigativeNote[]>(`/api/workspace/${caseId}/notes`),

  createNote: (caseId: string, note: Omit<InvestigativeNote, "id">) =>
    fetchAPI<InvestigativeNote>(`/api/workspace/${caseId}/notes`, {
      method: "POST",
      body: note,
    }),

  updateNote: (caseId: string, noteId: string, note: Partial<InvestigativeNote>) =>
    fetchAPI<InvestigativeNote>(`/api/workspace/${caseId}/notes/${noteId}`, {
      method: "PUT",
      body: note,
    }),

  deleteNote: (caseId: string, noteId: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/notes/${noteId}`, {
      method: "DELETE",
    }),

  // Theories
  getTheories: (caseId: string) =>
    fetchAPI<Theory[]>(`/api/workspace/${caseId}/theories`),

  createTheory: (caseId: string, theory: Omit<Theory, "id">) =>
    fetchAPI<Theory>(`/api/workspace/${caseId}/theories`, {
      method: "POST",
      body: theory,
    }),

  updateTheory: (caseId: string, theoryId: string, theory: Partial<Theory>) =>
    fetchAPI<Theory>(`/api/workspace/${caseId}/theories/${theoryId}`, {
      method: "PUT",
      body: theory,
    }),

  deleteTheory: (caseId: string, theoryId: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/theories/${theoryId}`, {
      method: "DELETE",
    }),

  buildTheoryGraph: (
    caseId: string,
    theoryId: string,
    options?: Record<string, unknown>
  ) =>
    fetchAPI<unknown>(
      `/api/workspace/${caseId}/theories/${theoryId}/build-graph`,
      { method: "POST", body: options }
    ),

  // Tasks
  getTasks: (caseId: string) =>
    fetchAPI<InvestigationTask[]>(`/api/workspace/${caseId}/tasks`),

  createTask: (caseId: string, task: Omit<InvestigationTask, "id">) =>
    fetchAPI<InvestigationTask>(`/api/workspace/${caseId}/tasks`, {
      method: "POST",
      body: task,
    }),

  updateTask: (caseId: string, taskId: string, task: Partial<InvestigationTask>) =>
    fetchAPI<InvestigationTask>(`/api/workspace/${caseId}/tasks/${taskId}`, {
      method: "PUT",
      body: task,
    }),

  deleteTask: (caseId: string, taskId: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/tasks/${taskId}`, {
      method: "DELETE",
    }),

  // Deadlines
  getDeadlines: (caseId: string) =>
    fetchAPI<DeadlineConfig>(`/api/workspace/${caseId}/deadlines`),

  updateDeadlines: (caseId: string, deadlineConfig: DeadlineConfig) =>
    fetchAPI<DeadlineConfig>(`/api/workspace/${caseId}/deadlines`, {
      method: "PUT",
      body: deadlineConfig,
    }),

  // Pinned Items
  getPinnedItems: (caseId: string) =>
    fetchAPI<PinnedItem[]>(`/api/workspace/${caseId}/pinned`),

  pinItem: (
    caseId: string,
    itemType: string,
    itemId: string,
    annotationsCount?: number
  ) => {
    const qs = new URLSearchParams({ item_type: itemType, item_id: itemId })
    if (annotationsCount !== undefined)
      qs.set("annotations_count", String(annotationsCount))
    return fetchAPI<PinnedItem>(`/api/workspace/${caseId}/pinned?${qs}`, {
      method: "POST",
    })
  },

  unpinItem: (caseId: string, pinId: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/pinned/${pinId}`, {
      method: "DELETE",
    }),

  // Presence
  getPresence: (caseId: string) =>
    fetchAPI<PresenceEntry[]>(`/api/workspace/${caseId}/presence`),

  updatePresence: (caseId: string, status: string) =>
    fetchAPI<void>(`/api/workspace/${caseId}/presence`, {
      method: "PUT",
      body: { status },
    }),

  // Investigation Timeline
  getInvestigationTimeline: (caseId: string) =>
    fetchAPI<unknown[]>(`/api/workspace/${caseId}/investigation-timeline`),

  getTheoryTimeline: (caseId: string, theoryId: string) =>
    fetchAPI<unknown[]>(
      `/api/workspace/${caseId}/theories/${theoryId}/timeline`
    ),
}
