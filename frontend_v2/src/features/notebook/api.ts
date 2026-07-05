import { fetchAPI } from "@/lib/api-client"

export type NotebookTargetType =
  | "entity"
  | "evidence"
  | "document"
  | "timeline_event"
  | "agent_artifact"

export interface NotebookLinkInput {
  target_type: NotebookTargetType
  target_id: string
  target_label?: string | null
  metadata?: Record<string, unknown>
}

export interface NotebookLink extends NotebookLinkInput {
  id: string
  note_id: string
  case_id: string
  created_at?: string | null
}

export interface NotebookNote {
  id: string
  case_id: string
  title?: string | null
  body: string
  tags: string[]
  visibility: string
  author_user_id?: string | null
  author_email?: string | null
  author_name?: string | null
  created_at?: string | null
  updated_at?: string | null
  links: NotebookLink[]
}

export interface NotebookNoteInput {
  title?: string | null
  body: string
  tags?: string[]
  links?: NotebookLinkInput[]
}

export interface NotebookNoteUpdate {
  title?: string | null
  body?: string
  tags?: string[]
  links?: NotebookLinkInput[]
}

export interface NotebookListParams {
  mine?: boolean
  q?: string
  linked_type?: NotebookTargetType
  linked_id?: string
  limit?: number
  offset?: number
}

export interface NotebookListResponse {
  notes: NotebookNote[]
  total: number
}

function buildQuery(params: NotebookListParams = {}) {
  const qs = new URLSearchParams()
  if (params.mine) qs.set("mine", "true")
  if (params.q?.trim()) qs.set("q", params.q.trim())
  if (params.linked_type) qs.set("linked_type", params.linked_type)
  if (params.linked_id) qs.set("linked_id", params.linked_id)
  if (params.limit != null) qs.set("limit", String(params.limit))
  if (params.offset != null) qs.set("offset", String(params.offset))
  const query = qs.toString()
  return query ? `?${query}` : ""
}

export const notebookAPI = {
  listNotes: (caseId: string, params: NotebookListParams = {}) =>
    fetchAPI<NotebookListResponse>(
      `/api/notebook/${encodeURIComponent(caseId)}/notes${buildQuery(params)}`
    ),

  listTargetNotes: (
    caseId: string,
    targetType: NotebookTargetType,
    targetId: string,
    limit = 20
  ) =>
    fetchAPI<NotebookListResponse>(
      `/api/notebook/${encodeURIComponent(caseId)}/targets/${encodeURIComponent(targetType)}/${encodeURIComponent(targetId)}/notes?limit=${limit}`
    ),

  createNote: (caseId: string, input: NotebookNoteInput) =>
    fetchAPI<NotebookNote>(`/api/notebook/${encodeURIComponent(caseId)}/notes`, {
      method: "POST",
      body: input,
    }),

  updateNote: (caseId: string, noteId: string, input: NotebookNoteUpdate) =>
    fetchAPI<NotebookNote>(
      `/api/notebook/${encodeURIComponent(caseId)}/notes/${encodeURIComponent(noteId)}`,
      {
        method: "PATCH",
        body: input,
      }
    ),

  deleteNote: (caseId: string, noteId: string) =>
    fetchAPI<void>(
      `/api/notebook/${encodeURIComponent(caseId)}/notes/${encodeURIComponent(noteId)}`,
      { method: "DELETE" }
    ),
}
