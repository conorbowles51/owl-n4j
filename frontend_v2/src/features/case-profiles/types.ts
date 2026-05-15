export const caseProfileTypes = [
  "person",
  "address",
  "event",
  "device",
  "organisation",
  "vehicle",
  "other",
] as const

export type CaseProfileType = (typeof caseProfileTypes)[number]

export const caseProfileAttributeKinds = [
  "alias",
  "tag",
  "phone",
  "email",
  "address",
  "identifier",
  "device",
  "vehicle",
  "organisation",
  "date",
  "custom",
] as const

export type CaseProfileAttributeKind = (typeof caseProfileAttributeKinds)[number]

export interface CaseProfileAttribute {
  id: string
  kind: CaseProfileAttributeKind
  name?: string | null
  value: string
  ordinal: number
}

export interface CaseProfileAttributeInput {
  kind: CaseProfileAttributeKind
  name?: string | null
  value: string
}

export interface CaseProfileGraphNodeLink {
  id: string
  node_key: string
  node_name?: string | null
  node_type?: string | null
  relationship_type?: string | null
  created_at?: string | null
}

export interface CaseProfileGraphNodeLinkInput {
  node_key: string
  node_name?: string | null
  node_type?: string | null
  relationship_type?: string | null
}

export interface CaseProfileEvidenceSummary {
  id: string
  case_id: string
  original_filename: string
  status: string
  summary?: string | null
  source_type?: string | null
  created_at?: string | null
  processed_at?: string | null
}

export interface CaseProfileEvidenceLink {
  id: string
  evidence_file_id: string
  relationship_type?: string | null
  excerpt?: string | null
  page?: number | null
  created_at?: string | null
  evidence?: CaseProfileEvidenceSummary | null
}

export interface CaseProfileEvidenceLinkInput {
  evidence_file_id: string
  relationship_type?: string | null
  excerpt?: string | null
  page?: number | null
}

export interface CaseProfileNoteLink {
  id: string
  note_id: string
  relationship_type?: string | null
  created_at?: string | null
}

export interface CaseProfileNoteLinkInput {
  note_id: string
  relationship_type?: string | null
}

export interface CaseProfileFindingLink {
  id: string
  finding_id: string
  relationship_type?: string | null
  created_at?: string | null
}

export interface CaseProfileFindingLinkInput {
  finding_id: string
  relationship_type?: string | null
}

export interface CaseProfile {
  id: string
  case_id: string
  profile_type: CaseProfileType
  display_name: string
  summary?: string | null
  importance?: string | null
  aliases: string[]
  tags: string[]
  attributes: CaseProfileAttribute[]
  graph_node_links: CaseProfileGraphNodeLink[]
  evidence_links: CaseProfileEvidenceLink[]
  note_links: CaseProfileNoteLink[]
  finding_links: CaseProfileFindingLink[]
  archived_at?: string | null
  created_by_user_id?: string | null
  updated_by_user_id?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface CaseProfileCreateInput {
  case_id: string
  profile_type: CaseProfileType
  display_name: string
  summary?: string | null
  importance?: string | null
  aliases?: string[]
  tags?: string[]
  attributes?: CaseProfileAttributeInput[]
  graph_node_links?: CaseProfileGraphNodeLinkInput[]
  evidence_links?: CaseProfileEvidenceLinkInput[]
  note_links?: CaseProfileNoteLinkInput[]
  finding_links?: CaseProfileFindingLinkInput[]
}

export type CaseProfileUpdateInput = Partial<
  Omit<CaseProfileCreateInput, "case_id">
>

export interface CaseProfilesListParams {
  caseId: string
  q?: string
  profileType?: CaseProfileType
  includeArchived?: boolean
  linkedGraphNodeKey?: string
  linkedEvidenceFileId?: string
  limit?: number
  offset?: number
}

export interface CaseProfilesListResponse {
  profiles: CaseProfile[]
  total: number
}

export interface CaseProfileLinkedWorkspaceRow {
  id: string
  title?: string | null
  content?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface CaseProfileContext {
  profile: CaseProfile
  graph_node_links: CaseProfileGraphNodeLink[]
  graph_nodes: Array<{
    link: CaseProfileGraphNodeLink
    node: Record<string, unknown> | null
  }>
  evidence_links: CaseProfileEvidenceLink[]
  notes: CaseProfileLinkedWorkspaceRow[]
  findings: CaseProfileLinkedWorkspaceRow[]
  timeline_nodes: Array<Record<string, unknown>>
}
