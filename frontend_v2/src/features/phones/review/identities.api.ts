import { fetchAPI } from "@/lib/api-client"

/** One identity in a case and the decisions on it (02 sections 8.5 to 8.8; 07 J-7). */
export interface IdentityName {
  phone: string | null
  name: string
  basis: string
  occurrences: number
  is_phone_name: boolean
}

export interface IdentityDetail {
  id: string
  identity_key: string
  kind: string
  subkind: string | null
  value_display: string
  sightings: number
  phones: number
  names: IdentityName[]
  linked_dossier: { id: string; name: string | null } | null
  can_be_a_person: boolean
  expected_revision: string
}

export interface SuggestionReason {
  reason: string
  weight: number
  records: string[]
  record_count: number
  phones: string[]
  names?: string[]
}

export interface IdentitySuggestion {
  id: string
  score: number
  dossier_id: string | null
  identities: { id: string; identity_key: string; kind: string; value_display: string }[]
  reasons: SuggestionReason[]
  /** strength on the app's one scale, by a stated rule (never a model) */
  level?: MatchLevel
  strength_reasons?: { match: string[]; substantiation: string[] }
  expected_revision: string
}

export type MatchLevel = "strong" | "moderate" | "weak" | "faint"

export type IdentityDecisionKind =
  | "link_phone_identity"
  | "unlink_phone_identity"
  | "split"
  | "reject_phone_identity_link"
  | "restore_phone_identity_link"

export interface IdentityDecisionBody {
  decision: IdentityDecisionKind
  identity_keys: string[]
  dossier_id?: string
  new_person_name?: string
  target_identity_key?: string
  reason?: string
  note?: string
  reasons_shown?: { reason: string }[]
  expected_revision?: string
}

const q = (caseId: string) => `case_id=${encodeURIComponent(caseId)}`

export const identitiesAPI = {
  get: (caseId: string, key: string) =>
    fetchAPI<IdentityDetail>(`/api/phones/identities/${encodeURIComponent(key)}?${q(caseId)}`),
  suggestions: (caseId: string) =>
    fetchAPI<{ case_id: string; total: number; decided?: number; suggestions: IdentitySuggestion[]; by_level?: Record<MatchLevel, number>; scale?: string }>(`/api/phones/identity-suggestions?${q(caseId)}`),
  decide: (caseId: string, body: IdentityDecisionBody) =>
    fetchAPI<{ decisions: string[]; dossier_id: string | null; revision: string }>("/api/phones/identity-decisions", {
      method: "POST",
      body: { case_id: caseId, ...body },
    }),
}
