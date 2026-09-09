import { fetchAPI } from "@/lib/api-client"

export interface DossierRole {
  id: string
  name: string
  is_builtin: boolean
  template_key?: string | null
}
export interface DossierLink {
  id: string
  target_type: string
  target_id: string
  relationship_type?: string | null
  label?: string | null
  source_anchor: Record<string, unknown>
  created_at?: string | null
}
export interface DossierEvidence {
  id: string
  original_filename: string
  status: string
  size: number
  sha256: string
  source_type?: string | null
  metadata: Record<string, unknown>
  file_url: string
}
export interface DossierMedia {
  id: string
  evidence_file_id: string
  is_cover: boolean
  ordinal: number
  caption?: string | null
  focal_x?: number | null
  focal_y?: number | null
  crop_metadata: Record<string, unknown>
  source_anchor: Record<string, unknown>
  evidence: DossierEvidence
  created_at?: string | null
}
export interface DossierAssessment {
  id: string
  category: string
  content: string
  assessment_date?: string | null
  author_user_id?: string | null
  updated_by_user_id?: string | null
  legacy_label?: string | null
  provenance_type?: "investigator" | "ai_assisted" | string
  generated_output_id?: string | null
  created_at?: string | null
  updated_at?: string | null
  supporting_links: DossierLink[]
}
export interface InterviewEvidenceLink {
  id: string
  evidence_file_id: string
  source_anchor: Record<string, unknown>
  evidence: DossierEvidence
}
export interface DossierInterview {
  id: string
  interview_date?: string | null
  participants: Array<Record<string, unknown> | string>
  interviewer_user_ids: string[]
  status: string
  working_notes?: string | null
  created_by_user_id?: string | null
  updated_by_user_id?: string | null
  created_at?: string | null
  updated_at?: string | null
  evidence_links: InterviewEvidenceLink[]
}
export interface CanonicalIdentity {
  key: string
  name?: string
  type?: string
  summary?: string
  verified_facts?: unknown[]
  properties?: Record<string, unknown>
  connections?: unknown[]
}
export interface Dossier {
  id: string
  case_id: string
  dossier_type: string
  display_name: string
  display_name_snapshot: string
  summary?: string | null
  importance?: string | null
  canonical_entity_key?: string | null
  linkage_state: "linked" | "unlinked" | "deleted"
  status: string
  needs_link_review: boolean
  graph_entity_deleted: boolean
  canonical_identity?: CanonicalIdentity | null
  roles: DossierRole[]
  archived_at?: string | null
  created_by_user_id?: string | null
  updated_by_user_id?: string | null
  created_at?: string | null
  updated_at?: string | null
  links?: DossierLink[]
  assessments?: DossierAssessment[]
  media?: DossierMedia[]
  interviews?: DossierInterview[]
}
export interface DossierListResponse {
  dossiers: Dossier[]
  total: number
  limit: number
  offset: number
}
export interface DossierCreateInput {
  case_id: string
  dossier_type?: string
  display_name?: string | null
  canonical_entity_key?: string | null
  summary?: string | null
  importance?: string | null
  status?: string
  roles?: Array<{ name: string; template_key?: string }>
}
export interface LinkInput {
  target_type: string
  target_id: string
  relationship_type?: string | null
  label?: string | null
  source_anchor?: Record<string, unknown>
}

function query(params: Record<string, unknown>) {
  const value = new URLSearchParams()
  Object.entries(params).forEach(([key, item]) => {
    if (item !== undefined && item !== null && item !== "" && item !== false)
      value.set(key, String(item))
  })
  return value.toString()
}

export const dossiersAPI = {
  list: (params: {
    caseId: string
    q?: string
    dossierType?: string
    linkageState?: string
    linkedEvidenceFileId?: string
    includeArchived?: boolean
    limit?: number
    offset?: number
  }) =>
    fetchAPI<DossierListResponse>(
      `/api/dossiers?${query({ case_id: params.caseId, q: params.q, dossier_type: params.dossierType, linkage_state: params.linkageState, linked_evidence_file_id: params.linkedEvidenceFileId, include_archived: params.includeArchived, limit: params.limit, offset: params.offset })}`
    ),
  get: (id: string) =>
    fetchAPI<Dossier>(`/api/dossiers/${encodeURIComponent(id)}`),
  create: (input: DossierCreateInput) =>
    fetchAPI<Dossier>("/api/dossiers", { method: "POST", body: input }),
  update: (
    id: string,
    input: Partial<Omit<DossierCreateInput, "case_id" | "canonical_entity_key">>
  ) =>
    fetchAPI<Dossier>(`/api/dossiers/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: input,
    }),
  link: (id: string, entityKey: string) =>
    fetchAPI<Dossier>(`/api/dossiers/${encodeURIComponent(id)}/link`, {
      method: "POST",
      body: { entity_key: entityKey },
    }),
  archive: (id: string) =>
    fetchAPI<Dossier>(`/api/dossiers/${encodeURIComponent(id)}/archive`, {
      method: "POST",
    }),
  restore: (id: string) =>
    fetchAPI<Dossier>(`/api/dossiers/${encodeURIComponent(id)}/restore`, {
      method: "POST",
    }),
  replaceLinks: (id: string, links: LinkInput[]) =>
    fetchAPI<Dossier>(`/api/dossiers/${encodeURIComponent(id)}/links`, {
      method: "PUT",
      body: { links },
    }),
  addEvidence: (id: string, evidenceFileIds: string[]) =>
    fetchAPI<Dossier>(`/api/dossiers/${encodeURIComponent(id)}/evidence`, {
      method: "POST",
      body: { evidence_file_ids: evidenceFileIds },
    }),
  removeEvidence: (id: string, evidenceFileId: string) =>
    fetchAPI<Dossier>(
      `/api/dossiers/${encodeURIComponent(id)}/evidence/${encodeURIComponent(evidenceFileId)}`,
      { method: "DELETE" }
    ),
  createAssessment: (
    id: string,
    input: {
      category: string
      content: string
      assessment_date?: string | null
      supporting_links?: LinkInput[]
    }
  ) =>
    fetchAPI<DossierAssessment>(
      `/api/dossiers/${encodeURIComponent(id)}/assessments`,
      { method: "POST", body: input }
    ),
  deleteAssessment: (id: string, assessmentId: string) =>
    fetchAPI<void>(
      `/api/dossiers/${encodeURIComponent(id)}/assessments/${encodeURIComponent(assessmentId)}`,
      { method: "DELETE" }
    ),
  addMedia: (
    id: string,
    input: {
      evidence_file_id: string
      is_cover?: boolean
      caption?: string
      focal_x?: number
      focal_y?: number
      source_anchor?: Record<string, unknown>
    }
  ) =>
    fetchAPI<DossierMedia>(`/api/dossiers/${encodeURIComponent(id)}/media`, {
      method: "POST",
      body: input,
    }),
  updateMedia: (
    id: string,
    mediaId: string,
    input: Partial<
      Pick<
        DossierMedia,
        | "is_cover"
        | "ordinal"
        | "caption"
        | "focal_x"
        | "focal_y"
        | "crop_metadata"
        | "source_anchor"
      >
    >
  ) =>
    fetchAPI<DossierMedia>(
      `/api/dossiers/${encodeURIComponent(id)}/media/${encodeURIComponent(mediaId)}`,
      { method: "PATCH", body: input }
    ),
  deleteMedia: (id: string, mediaId: string) =>
    fetchAPI<void>(
      `/api/dossiers/${encodeURIComponent(id)}/media/${encodeURIComponent(mediaId)}`,
      { method: "DELETE" }
    ),
  reorderMedia: (id: string, mediaIds: string[]) =>
    fetchAPI<DossierMedia[]>(
      `/api/dossiers/${encodeURIComponent(id)}/media-order`,
      { method: "PUT", body: { media_ids: mediaIds } }
    ),
  createInterview: (
    id: string,
    input: {
      interview_date?: string | null
      participants?: Array<Record<string, unknown> | string>
      interviewer_user_ids?: string[]
      status?: string
      working_notes?: string | null
      evidence_links?: Array<{
        evidence_file_id: string
        source_anchor?: Record<string, unknown>
      }>
    }
  ) =>
    fetchAPI<DossierInterview>(
      `/api/dossiers/${encodeURIComponent(id)}/interviews`,
      { method: "POST", body: input }
    ),
  updateInterview: (
    id: string,
    interviewId: string,
    input: Partial<DossierInterview>
  ) =>
    fetchAPI<DossierInterview>(
      `/api/dossiers/${encodeURIComponent(id)}/interviews/${encodeURIComponent(interviewId)}`,
      { method: "PATCH", body: input }
    ),
  deleteInterview: (id: string, interviewId: string) =>
    fetchAPI<void>(
      `/api/dossiers/${encodeURIComponent(id)}/interviews/${encodeURIComponent(interviewId)}`,
      { method: "DELETE" }
    ),
}
