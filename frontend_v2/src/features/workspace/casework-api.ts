import { fetchAPI } from "@/lib/api-client"

export type CaseworkEntryType = "note" | "finding" | "theory"
export type FindingSignificance = "high" | "medium" | "low"
export type LinkRelationship =
  | "unclassified"
  | "supports"
  | "contradicts"
  | "context"
export type CaseworkLinkTargetType =
  | "evidence"
  | "graph_entity"
  | "dossier"
  | "entry"
  | "task"
  | "deadline"
  | "timeline_event"
  | "agent_artifact"
  | "witness"

export interface CaseworkLinkInput {
  target_type: CaseworkLinkTargetType
  target_id: string
  target_label?: string | null
  relationship?: LinkRelationship
  source_anchor?: Record<string, unknown>
  metadata?: Record<string, unknown>
}

export interface CaseworkLink extends Required<
  Omit<CaseworkLinkInput, "target_label">
> {
  id: string
  entry_id: string
  case_id: string
  target_label?: string | null
  created_by_user_id?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface CaseworkRevision {
  id: string
  entry_id: string
  revision_number: number
  entry_type: CaseworkEntryType
  title?: string | null
  body: string
  tags: string[]
  lifecycle_state?: string | null
  significance?: FindingSignificance | null
  confidence?: number | null
  confidence_rationale?: string | null
  review_state: "accepted" | "pending" | "rejected"
  editor_user_id?: string | null
  editor_email?: string | null
  editor_name?: string | null
  created_at: string
}

export interface CaseworkEvent {
  id: string
  entry_id: string
  event_type: string
  before_state: Record<string, unknown>
  after_state: Record<string, unknown>
  rationale?: string | null
  actor_user_id?: string | null
  actor_email?: string | null
  actor_name?: string | null
  created_at: string
}

export interface CaseworkEntry {
  id: string
  case_id: string
  entry_type: CaseworkEntryType
  title?: string | null
  body: string
  tags: string[]
  lifecycle_state?: string | null
  significance?: FindingSignificance | null
  confidence?: number | null
  confidence_rationale?: string | null
  review_state: "accepted" | "pending" | "rejected"
  author_user_id?: string | null
  author_email?: string | null
  author_name?: string | null
  updated_by_user_id?: string | null
  updated_by_email?: string | null
  updated_by_name?: string | null
  version: number
  source_theory_entry_id?: string | null
  legacy_source?: string | null
  legacy_id?: string | null
  migration_metadata: Record<string, unknown>
  needs_migration_review: boolean
  deleted_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  links: CaseworkLink[]
  revisions?: CaseworkRevision[]
  events?: CaseworkEvent[]
}

export interface CaseworkListParams {
  tag?: string
  entry_type?: CaseworkEntryType
  lifecycle_state?: string
  significance?: FindingSignificance
  confidence_min?: number
  confidence_max?: number
  author_user_id?: string
  q?: string
  updated_since?: string
  include_deleted?: boolean
  sort_by?:
    | "updated_at"
    | "created_at"
    | "title"
    | "confidence"
    | "significance"
  sort_direction?: "asc" | "desc"
  limit?: number
  offset?: number
}

export interface CaseworkListResponse {
  entries: CaseworkEntry[]
  total: number
}

export interface CaseworkCreateInput {
  entry_type: CaseworkEntryType
  title?: string | null
  body: string
  tags?: string[]
  lifecycle_state?: string | null
  significance?: FindingSignificance | null
  confidence?: number | null
  confidence_rationale?: string | null
  links?: CaseworkLinkInput[]
}

export interface CaseworkUpdateInput {
  expected_version: number
  title?: string | null
  body?: string
  tags?: string[]
  links?: CaseworkLinkInput[]
}

export interface AttachmentOption {
  target_type: CaseworkLinkTargetType
  target_id: string
  label: string
  description?: string | null
  metadata: Record<string, unknown>
}

export interface CaseworkAuthor {
  user_id: string
  name?: string | null
  email?: string | null
  label: string
}

function queryString(params: object) {
  const query = new URLSearchParams()
  Object.entries(params as Record<string, unknown>).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      if (Array.isArray(value)) {
        value.forEach((item) => query.append(key, String(item)))
      } else {
        query.set(key, String(value))
      }
    }
  })
  const rendered = query.toString()
  return rendered ? `?${rendered}` : ""
}

const base = (caseId: string) => `/api/workspace/${encodeURIComponent(caseId)}`

export const caseworkAPI = {
  list: (caseId: string, params: CaseworkListParams = {}) =>
    fetchAPI<CaseworkListResponse>(
      `${base(caseId)}/entries${queryString(params)}`
    ),

  get: (caseId: string, entryId: string, includeDeleted = false) =>
    fetchAPI<CaseworkEntry>(
      `${base(caseId)}/entries/${encodeURIComponent(entryId)}${queryString({ include_deleted: includeDeleted })}`
    ),

  create: (caseId: string, input: CaseworkCreateInput) =>
    fetchAPI<CaseworkEntry>(`${base(caseId)}/entries`, {
      method: "POST",
      body: input,
    }),

  update: (caseId: string, entryId: string, input: CaseworkUpdateInput) =>
    fetchAPI<CaseworkEntry>(
      `${base(caseId)}/entries/${encodeURIComponent(entryId)}`,
      { method: "PATCH", body: input }
    ),

  changeLifecycle: (
    caseId: string,
    entryId: string,
    expectedVersion: number,
    lifecycleState: string,
    rationale?: string
  ) =>
    fetchAPI<CaseworkEntry>(
      `${base(caseId)}/entries/${encodeURIComponent(entryId)}/lifecycle`,
      {
        method: "POST",
        body: {
          expected_version: expectedVersion,
          lifecycle_state: lifecycleState,
          rationale,
        },
      }
    ),

  changeConfidence: (
    caseId: string,
    entryId: string,
    expectedVersion: number,
    confidence: number | null,
    rationale?: string
  ) =>
    fetchAPI<CaseworkEntry>(
      `${base(caseId)}/entries/${encodeURIComponent(entryId)}/confidence`,
      {
        method: "POST",
        body: { expected_version: expectedVersion, confidence, rationale },
      }
    ),

  changeSignificance: (
    caseId: string,
    entryId: string,
    expectedVersion: number,
    significance: FindingSignificance
  ) =>
    fetchAPI<CaseworkEntry>(
      `${base(caseId)}/entries/${encodeURIComponent(entryId)}/significance`,
      {
        method: "POST",
        body: { expected_version: expectedVersion, significance },
      }
    ),

  convertToFinding: (
    caseId: string,
    entryId: string,
    expectedVersion: number,
    significance: FindingSignificance,
    draft?: { title: string; body: string }
  ) =>
    fetchAPI<{ theory: CaseworkEntry; finding: CaseworkEntry }>(
      `${base(caseId)}/entries/${encodeURIComponent(entryId)}/convert-to-finding`,
      {
        method: "POST",
        body: { expected_version: expectedVersion, significance, ...draft },
      }
    ),

  delete: (caseId: string, entryId: string, expectedVersion: number) =>
    fetchAPI<void>(
      `${base(caseId)}/entries/${encodeURIComponent(entryId)}${queryString({ expected_version: expectedVersion })}`,
      { method: "DELETE" }
    ),

  restore: (caseId: string, entryId: string, expectedVersion: number) =>
    fetchAPI<CaseworkEntry>(
      `${base(caseId)}/entries/${encodeURIComponent(entryId)}/restore`,
      { method: "POST", body: { expected_version: expectedVersion } }
    ),

  attachmentOptions: (
    caseId: string,
    targetType: CaseworkLinkTargetType,
    q = "",
    limit = 20,
    targetIds?: string[]
  ) =>
    fetchAPI<{ items: AttachmentOption[] }>(
      `${base(caseId)}/attachment-options${queryString({ target_type: targetType, q, limit, target_ids: targetIds })}`
    ),

  authors: (caseId: string) =>
    fetchAPI<CaseworkAuthor[]>(`${base(caseId)}/entry-authors`),
}
