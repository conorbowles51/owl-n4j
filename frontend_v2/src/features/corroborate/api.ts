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

export interface Preview {
  members: number
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

const base = (caseId: string) => `/api/cases/${encodeURIComponent(caseId)}/corroborate`

export const corroborateAPI = {
  preview: (caseId: string, members: RelationMember[]) =>
    fetchAPI<Preview>(`${base(caseId)}/preview`, { method: "POST", body: { members } }),
  matchList: (caseId: string, text: string) => fetchAPI<ListMatch>(`${base(caseId)}/match-list`, { method: "POST", body: { text } }),
}
