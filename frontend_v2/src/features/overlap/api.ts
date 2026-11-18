import { fetchAPI } from "@/lib/api-client"
import type { RelationMember } from "@/features/relations/api"

/** Backend routers/overlap_views.py (lx-overlapviews-b): read-only, case view. */
const base = (caseId: string) => `/api/cases/${encodeURIComponent(caseId)}/corroborate`

export interface TimeGroup { time: string; nights: string[]; stay_min: number }
export interface AreaPhone { phone: string; who: string; nights: string[]; times: TimeGroup[]; first: Record<string, string> }
export interface AreaResult {
  index: number
  label: string
  inside: { positions: number; position_phones: number; access_rows: number; doors: Record<string, number>; photo_places: number; photo_phones: number; not_positions: number }
  baseline: { positions: number; access_rows: number; photo_places: number; nights_with_any: number }
  phones: AreaPhone[]
  photo_only: { phone: string; who: string; nights: string[] }[]
  access: { person: string; who: string; nights: string[]; times: { time: string; door: string | null; nights: number }[] }[]
  outside_window: { phone: string; who: string; days: number; positions: number; from: string; to: string; usual_hour: string }[]
  documents: { id: string; name: string; why: string }[]
  suggested_documents: { id: string; name: string; why: string }[]
}
export interface StripItem { area: number; at: string; who: string; phone?: string; what: "position" | "photo_place" | "not_position" | "access_row"; door?: string | null; ref: string; text?: string }
export interface AreaCompare {
  zone: string
  window: { weekday: number; start: string; end: string; words: string }
  period: { from: string; to: string }
  asked: { nights: string[]; basis: string; unknown: string[] }
  compared_with: { nights: string[]; words: string }
  areas: AreaResult[]
  order: { phone: string; who: string; sequence: number[]; nights: number; of: number }[]
  strip: { night: string; label: string; asked: boolean; areas: StripItem[] }[]
  members: RelationMember[]
  documents_available: { id: string; name: string }[]
}
export interface AreaCompareRequest {
  areas: { label: string; ring: number[][] }[]
  weekday: number
  start: string
  end: string
  nights?: string[] | null
  documents?: Record<number, string[]> | null
}

export interface SharedPhrase { text: string; words: string; copies: number; messages: number; phones: string[]; phone_labels: string[]; dates: string[]; stock: boolean; why: string | null; records: string[] }
export interface SharedContent {
  zone: string
  phones_in_case: number
  rule: string
  also: SharedPhrase[]
  stock: SharedPhrase[]
  deletions: { text: string; at: string; deleted_on: string[]; kept_on: string[]; records: string[] }[]
}
export interface SharedFiles {
  phones_in_case: number
  listed: number
  counts: { files_common: number; files_shared: number; lookalikes: number }
  files_common: { md5: string; name: string; phones: string[] }[]
  files_shared: { md5: string; name: string; phones: string[] }[]
  lookalikes: { a: { name: string; phone: string; file_uid: string }; b: { name: string; phone: string; file_uid: string }; bits_apart: number; level: string }[]
  lookalike_note: string | null
}
export interface ThreadMarks {
  zone: string
  marks: Record<string, { shared: { stock: boolean; why: string | null; copies: number; messages: number; dates: number; phones: number; other_phones: string[] } }>
  meanwhile: Record<string, { record_uid: string; at: string; time: string; phone: string; body: string; direction: string }[]>
  names: { number: string; names: { phone: string; name: string }[]; own_number_of: string | null; note: string }[]
}

export interface MoneyCell {
  amount_minor: number
  amount: string
  day: string
  source: "bank_and_phone" | "phone_only" | "bank_only"
  words: string
  check: number | null
  records: string[]
  banks: string[]
  gap?: { person: string; month: string; words: string; statements: { file_id: string; name: string; pages_missing: number[] }[] } | null
}
export interface MoneyColumn { id: string; title: string; kind: "transfer" | "cash" | "check"; payer: string | null; payee: string | null; usual_day: number; events: number; of: number; total_minor: number; checks: [number, number] | null; ordinary: boolean; other_weeks_found: number }
export interface AroundEvent {
  zone: string
  span_days: number
  events: { date: string; label: string }[]
  columns: MoneyColumn[]
  rows: { date: string; label: string; cells: Record<string, MoneyCell[]> }[]
  other_weeks: { weeks: number; from: string | null; to: string | null; found: Record<string, MoneyCell[]> } | null
  one_off: MoneyCell[]
  rule: string
}
export interface EventChoice { date: string; label: string; from: string; words: string | null; reading?: string | null }

export const overlapAPI = {
  areaCompare: (caseId: string, body: AreaCompareRequest) =>
    fetchAPI<AreaCompare>(`${base(caseId)}/area-compare`, { method: "POST", body }),
  sharedWords: (caseId: string) => fetchAPI<SharedContent>(`${base(caseId)}/shared-words`),
  sharedFiles: (caseId: string) => fetchAPI<SharedFiles>(`${base(caseId)}/shared-words/files`, { timeout: 900_000 }),
  threadMarks: (caseId: string, extractionId: string, threadKey: string) =>
    fetchAPI<ThreadMarks>(`${base(caseId)}/shared-words/thread?extraction_id=${encodeURIComponent(extractionId)}&thread_key=${encodeURIComponent(threadKey)}`),
  aroundEvent: (caseId: string, events: { date: string; label?: string }[]) =>
    fetchAPI<AroundEvent>(`${base(caseId)}/around-event`, { method: "POST", body: { events } }),
  eventChoices: (caseId: string) => fetchAPI<{ choices: EventChoice[] }>(`${base(caseId)}/around-event/choices`),
}
