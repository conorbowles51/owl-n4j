import { fetchAPI } from "@/lib/api-client"

/** A removal kept so it can be undone (backend services/removed_records). */
export interface RemovedRecord {
  id: string
  kind:
    | "dossier_assessment"
    | "dossier_interview"
    | "dossier_media"
    | "dossier_link"
    | "dossier_evidence_link"
  subject_id: string
  label?: string | null
  removed_by?: string | null
  removed_at?: string | null
  restored_at?: string | null
  dossier_id?: string | null
}
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
  /** CO-18: accepted from machine text (a transcript or text read from an image): which text, and the reader. */
  derived_text_id?: string | null
  read_by?: string | null
  created_at?: string | null
  updated_at?: string | null
  supporting_links: DossierLink[]
}
export interface InterviewEvidenceLink {
  id: string
  /** Set for an evidence file; null for a registry target such as a phone record. */
  evidence_file_id: string | null
  /** "evidence", or a registry type (phone_record, phone_analysis, statement_check). */
  target_type?: string
  target_id?: string
  source_anchor: Record<string, unknown>
  evidence: DossierEvidence | null
}
export type InterviewEvidenceInput =
  | { evidence_file_id: string; source_anchor?: Record<string, unknown> }
  | {
      target_type: string
      target_id: string
      source_anchor?: Record<string, unknown>
    }
export interface DossierInterview {
  id: string
  date_value?: string | null
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
export interface DossierContact {
  id?: string | null
  kind: "phone" | "email" | "address"
  label?: string | null
  value: string
  evidence_file_id?: string | null
  recorded_by_user_id?: string | null
  /** Where the detail came from; a contact copied from a phone names its phone record. Sent back unchanged. */
  record_source?: {
    type: "manual" | "evidence" | "phone_record"
    target_id?: string
    mapping_versions?: Record<string, unknown>
  } | null
}
export interface Dossier {
  id: string
  case_id: string
  dossier_type: string
  display_name: string
  display_name_snapshot: string
  summary?: string | null
  contacts?: DossierContact[]
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
  /** Entry-owned references. Managed in the entry, never removed through dossier links. */
  incoming_casework?: Array<{ id: string; title: string; entry_type: "note" | "finding" | "theory"; relationship: string }>
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
  contacts?: DossierContact[]
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
    canonicalEntityKey?: string
    linkedEvidenceFileId?: string
    linkedEntryId?: string
    includeArchived?: boolean
    limit?: number
    offset?: number
  }) =>
    fetchAPI<DossierListResponse>(
      `/api/dossiers?${query({ case_id: params.caseId, q: params.q, dossier_type: params.dossierType, linkage_state: params.linkageState, linked_evidence_file_id: params.linkedEvidenceFileId, linked_entry_id: params.linkedEntryId, canonical_entity_key: params.canonicalEntityKey, include_archived: params.includeArchived, limit: params.limit, offset: params.offset })}`
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
  addLinks: (id: string, links: LinkInput[]) =>
    fetchAPI<{
      dossier_id: string
      added: number
      skipped: number
      added_link_ids: string[]
      total_links: number
    }>(`/api/dossiers/${encodeURIComponent(id)}/links:add`, {
      method: "POST",
      body: { links, origin: "dossier_casework" },
    }),
  addEvidence: (id: string, evidenceFileIds: string[]) =>
    fetchAPI<Dossier>(`/api/dossiers/${encodeURIComponent(id)}/evidence`, {
      method: "POST",
      body: { evidence_file_ids: evidenceFileIds },
    }),
  /** Removes one link (a phone message, a note, any item) from the dossier; the item itself is unchanged. */
  removeLink: (id: string, linkId: string) =>
    fetchAPI<{ dossier_id: string; removed: number }>(
      `/api/dossiers/${encodeURIComponent(id)}/links/${encodeURIComponent(linkId)}`,
      { method: "DELETE" }
    ),
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
      date_value?: string | null
      interview_date?: string | null
      participants?: Array<Record<string, unknown> | string>
      interviewer_user_ids?: string[]
      status?: string
      working_notes?: string | null
      evidence_links?: InterviewEvidenceInput[]
    }
  ) =>
    fetchAPI<DossierInterview>(
      `/api/dossiers/${encodeURIComponent(id)}/interviews`,
      { method: "POST", body: input }
    ),
  updateInterview: (
    id: string,
    interviewId: string,
    input: Partial<Omit<DossierInterview, "evidence_links">> & {
      evidence_links?: InterviewEvidenceInput[]
    }
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
  removed: (caseId: string, id: string) =>
    fetchAPI<{ items: RemovedRecord[]; clipped?: string }>(
      `/api/cases/${encodeURIComponent(caseId)}/removed-records?dossier_id=${encodeURIComponent(id)}`
    ),
  putBack: (caseId: string, removedId: string) =>
    fetchAPI<RemovedRecord>(
      `/api/cases/${encodeURIComponent(caseId)}/removed-records/${encodeURIComponent(removedId)}/restore`,
      { method: "POST" }
    ),
}
