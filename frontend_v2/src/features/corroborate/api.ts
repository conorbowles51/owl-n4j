import { fetchAPI } from "@/lib/api-client"
import type { RelationMember } from "@/features/relations/api"

/** Backend routers/corroborate.py: what Loupe takes from a selection, and a pasted list matched to the case. */
export interface QuestionChips {
  when: string
  nights: string
  who: string
  what: string
  compare_with: string
}

export interface SuggestedQuestion {
  kind: string
  text: string
  count: number
  count_words: string
  chips: QuestionChips
  /** From the engine (lx-corroengine): what the question checks and the comparison Loupe chose, with its count. */
  checks?: { signal: string; words: string }[]
  comparison?: { kind: string; words: string; count: number }
}

export interface Scope {
  from?: string
  to?: string
  zone?: string
  recurring?: { weekday: number | null; from_hour: number; to_hour: number }
  /** An exact window of instants, set by a preset round an incident time. */
  window?: { from_at: string; to_at: string; label?: string }
  relative?: { anchor_kind: string; person?: string; before_min: number; after_min: number }
  kinds?: string[]
  people?: string[]
}

export function scopeIsEmpty(s: Scope): boolean {
  return !s.from && !s.to && !s.window && !s.recurring && !s.relative && !(s.kinds?.length) && !(s.people?.length)
}

export interface Preview {
  members: number
  selected: number
  scope: { active: boolean; words: string[]; outside: Record<string, number>; outside_total: number; no_time: number; anchors: number | null; anchors_date_only: number; kept: { type: string; id: string }[] | null }
  left_out: { count: number; examples: string[] }
  taken: {
    people: { key: string; label: string; count: number }[]
    times: { from: string | null; to: string | null; dated: number; days: number; undated: number }
    places: { label: string; count: number }[]
    items: { type: string; count: number; words: string }[]
  }
  questions: SuggestedQuestion[]
}

export interface ListMatch {
  tokens: { token: string; kind: string; matched: number; unmatched_reason: string | null; via: string[] }[]
  members: RelationMember[]
  matched: number
  unmatched: { token: string; kind: string; unmatched_reason: string | null }[]
}

export interface AreaSelection {
  members: RelationMember[]
  phones: number
  places: number
  by_kind: Record<string, number>
  total: number
}

export interface Incident {
  date: string
  time: string | null
  words: string
  entry_id: string
  entry_type: string
  title: string
}

export interface Subset {
  id: string
  name: string
  member_count: number
  created_at: string | null
}

export interface Combined {
  members: RelationMember[]
  count: number
  first: number
  second: number
  words: string
}

/** lx-corrostatement's claim call: a sentence read into chips that nothing runs on until a person confirms them. */
export interface ClaimChip {
  value: string | null
  words: string | null
  confidence: number | string | null
  read_by: string
}
export type ClaimField = "who" | "when" | "where" | "what"
export interface Claim {
  id: string
  status: "draft" | "confirmed"
  sentence: string
  chips: Record<ClaimField, ClaimChip>
  missing: ClaimField[]
}

const base = (caseId: string) => `/api/cases/${encodeURIComponent(caseId)}/corroborate`

export const corroborateAPI = {
  preview: (caseId: string, members: RelationMember[], scope?: Scope) =>
    fetchAPI<Preview>(`${base(caseId)}/preview`, { method: "POST", body: { members, ...(scope ? { scope } : {}) } }),
  run: (caseId: string, body: { members: RelationMember[]; question: Record<string, unknown>; surface: string }) =>
    fetchAPI<{ group: { id: string; member_count: number; left_out: number } }>(`${base(caseId)}/run`, { method: "POST", body }),
  area: (caseId: string, areas: number[][][]) => fetchAPI<AreaSelection>(`${base(caseId)}/area`, { method: "POST", body: { areas } }),
  incidents: (caseId: string) => fetchAPI<{ incidents: Incident[] }>(`${base(caseId)}/incidents`),
  subsets: (caseId: string) => fetchAPI<{ subsets: Subset[] }>(`${base(caseId)}/subsets`),
  saveSubset: (caseId: string, name: string, members: RelationMember[]) =>
    fetchAPI<{ id: string; member_count: number }>(`${base(caseId)}/subsets`, { method: "POST", body: { name, members } }),
  combine: (caseId: string, first: string, second: string, op: string) =>
    fetchAPI<Combined>(`${base(caseId)}/subsets/combine`, { method: "POST", body: { first, second, op } }),
  parseClaim: (caseId: string, body: { text: string; statement_date?: string; source?: { type: string; id: string; label?: string } }) =>
    fetchAPI<{ claim: Claim }>(`${base(caseId)}/claims/parse`, { method: "POST", body }),
  confirmClaim: (caseId: string, id: string, chips: Record<ClaimField, ClaimChip>) =>
    fetchAPI<{ claim: Claim }>(`${base(caseId)}/claims/${encodeURIComponent(id)}:confirm`, { method: "POST", body: { chips } }),
  matchList: (caseId: string, text: string) => fetchAPI<ListMatch>(`${base(caseId)}/match-list`, { method: "POST", body: { text } }),
}

/** A free-text claim read into chips (lx-corrostatement). Loupe's reading is "Read by Loupe · not confirmed" until a person confirms it. */
export interface ClaimChip<V> {
  status: "read" | "not_stated" | "not_located" | "unread"
  value: V | null
  words: string | null
  confidence: string | null
  source: string
  read_by: string
  note?: string
}
export interface ClaimWho { key: string; label: string; words?: string; how?: string }
export interface ClaimWhen { start: string; end: string; zone: string; label: string }
export interface ClaimWhere { name: string; lat?: number; lon?: number; radius_m?: number; located?: boolean; how?: string }
export interface ClaimWhat { action: "presence" | "contact" | "with"; negated: boolean; with: string[]; mode?: string }
export interface ParsedClaim {
  id: string
  status: "draft" | "confirmed"
  sentence: string
  zone: string
  people: { key: string; label: string }[]
  read_by: string
  missing: string[]
  chips: { who: ClaimChip<ClaimWho[]>; when: ClaimChip<ClaimWhen>; where: ClaimChip<ClaimWhere>; what: ClaimChip<ClaimWhat> }
}
export interface ConfirmedChips { who: ClaimWho[]; when: ClaimWhen | null; where: ClaimWhere | null; what: ClaimWhat | null; where_text?: string }

export const claimAPI = {
  parse: (caseId: string, body: { text: string; statement_date?: string; speaker?: string; source?: Record<string, unknown> }) =>
    fetchAPI<{ claim: ParsedClaim }>(`${base(caseId)}/claims/parse`, { method: "POST", body }),
  confirm: (caseId: string, claimId: string, chips: ConfirmedChips) =>
    fetchAPI<{ claim: { id: string; status: string } }>(`${base(caseId)}/claims/${encodeURIComponent(claimId)}:confirm`, { method: "POST", body: { chips } }),
}
