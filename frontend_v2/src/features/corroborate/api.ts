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
}

export interface Scope {
  from?: string
  to?: string
  zone?: string
  recurring?: { weekday: number | null; from_hour: number; to_hour: number }
  kinds?: string[]
  people?: string[]
}

export function scopeIsEmpty(s: Scope): boolean {
  return !s.from && !s.to && !s.recurring && !(s.kinds?.length) && !(s.people?.length)
}

export interface Preview {
  members: number
  selected: number
  scope: { active: boolean; words: string[]; outside: Record<string, number>; outside_total: number; no_time: number; kept: { type: string; id: string }[] | null }
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

const base = (caseId: string) => `/api/cases/${encodeURIComponent(caseId)}/corroborate`

export const corroborateAPI = {
  preview: (caseId: string, members: RelationMember[], scope?: Scope) =>
    fetchAPI<Preview>(`${base(caseId)}/preview`, { method: "POST", body: { members, ...(scope ? { scope } : {}) } }),
  area: (caseId: string, areas: number[][][]) => fetchAPI<AreaSelection>(`${base(caseId)}/area`, { method: "POST", body: { areas } }),
  matchList: (caseId: string, text: string) => fetchAPI<ListMatch>(`${base(caseId)}/match-list`, { method: "POST", body: { text } }),
}
