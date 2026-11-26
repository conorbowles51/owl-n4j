import { fetchAPI } from "@/lib/api-client"
import type { StreamRow } from "../schemas"

/** Screen 3 (one person across every phone) and screen 4 (around a moment): GET /api/phones/person-across and
 * GET /api/phones/moment. Every count is the server's; the screens only draw them. */

export interface PersonPhoneCard {
  extraction_id: string
  label: string
  owner: string | null
  is_own: boolean
  owner_key: string | null
  saved_as: string[]
  messages: number
  calls: number
  first: string | null
  last: string | null
  conversations_href: string
}

export interface PersonRecord {
  row: StreamRow
  on: string[]
  missing: { extraction_id: string; not_recording: boolean }[]
  deleted_on: string[]
  copies: { extraction_id: string; record_uid: string; event_uid: string; at: string | null; deleted: boolean }[]
  spread_s: number
  diff: ("missing" | "deleted" | "clocks")[]
}

export interface Difference {
  code: "missing" | "deleted" | "names" | "clocks"
  title: string
  n: number
  body: string
  explained?: number
}

export interface NextStep {
  code: string
  rank: number
  title: string
  why: string
  action: string
  filter?: string
  phones?: string[]
  href?: string
  from?: string
  to?: string
  record_uid?: string
}

export type OnlyList = "missing" | "missing_unexplained" | "missing_not_recording" | "deleted" | "clocks"

export interface PersonAcross {
  case_id: string
  person: { name: string; identifiers: string[]; name_basis: string; keys: string[]; own_phones: string[] }
  with: { name: string; keys: string[] } | null
  phones: PersonPhoneCard[]
  zone: string
  summary: { messages: number; calls: number; apps: string[]; phones_holding: number; phones_in_scope: number; first: string | null; last: string | null; no_time: number; copies: number }
  records: PersonRecord[]
  records_total: number
  contacts_total: number
  only: OnlyList | null
  offset: number
  limit: number
  compare: { on: string[]; messages: number; calls: number }[]
  volume: { bucket: "month" | "week"; rows: { start: string; by_phone: Record<string, number> }[] }
  differs: Difference[]
  places: { own_phones: string[]; squares: { extraction_id: string; lat: number; lon: number; observations: number; first: string | null; last: string | null }[]; observations: number; words: string }
  next_steps: NextStep[]
  rule_words: string
}

export interface PersonQuery {
  caseId: string
  people: string[]
  phones?: string[]
  withPeople?: string[]
  only?: OnlyList | null
  offset?: number
  limit?: number
}

export function personAcrossQuery(p: PersonQuery) {
  return {
    queryKey: ["phone-person-across", p.caseId, p.people, p.phones ?? [], p.withPeople ?? [], p.only ?? null, p.offset ?? 0, p.limit ?? 200],
    queryFn: ({ signal }: { signal?: AbortSignal }) => {
      const q = new URLSearchParams({ case_id: p.caseId, people: p.people.join(",") })
      if (p.phones?.length) q.set("phones", p.phones.join(","))
      if (p.withPeople?.length) q.set("with", p.withPeople.join(","))
      if (p.only) q.set("only", p.only)
      if (p.offset) q.set("offset", String(p.offset))
      if (p.limit) q.set("limit", String(p.limit))
      return fetchAPI<PersonAcross>(`/api/phones/person-across?${q}`, { signal })
    },
  }
}

export interface MomentRecord {
  kind: "message" | "call" | "place" | "not_recording"
  at: string
  end?: string
  on: string[]
  app: string | null
  who: string | null
  text: string
  deleted_on: string[]
  record_uids: string[]
}

export interface MomentPhone {
  extraction_id: string
  label: string
  owner: string | null
  not_recording: { start: string; end: string }[]
  marks: { kind: "message" | "call" | "place" | "use"; at: string; record_uid: string | null }[]
  counts: { messages: number; calls: number; places: number; use: number }
}

export type StripState = "together" | "maybe" | "apart" | "unknown"

export interface Moment {
  case_id: string
  from: string
  to: string
  zone: string
  phones: MomentPhone[]
  pairs: { phones: [string, string]; strip: { start: string; end: string; state: StripState }[]; episodes: { kind: "together" | "apart"; start: string; end: string; breadth: string | null; items: number }[]; compared: number; words: string }[]
  records: MomentRecord[]
  places: { extraction_id: string; at: string; lat: number; lon: number; radius_m: number | null; record_uid: string | null }[]
  summary: string
  strip_words: Record<StripState, string>
  together_rule: string
  next_steps: NextStep[]
}

export function momentQuery(caseId: string, from: string, to: string, phones?: string[]) {
  return {
    queryKey: ["phone-moment", caseId, from, to, phones ?? []],
    queryFn: ({ signal }: { signal?: AbortSignal }) => {
      const q = new URLSearchParams({ case_id: caseId, from, to })
      if (phones?.length) q.set("phones", phones.join(","))
      return fetchAPI<Moment>(`/api/phones/moment?${q}`, { signal })
    },
  }
}

/** Screen addresses (shared with the other phone screens through phone-links). */
export function personHref(caseId: string, people: string[], phones: string[] = [], withPeople: string[] = []) {
  const q = new URLSearchParams({ people: people.join(",") })
  if (phones.length) q.set("phones", phones.join(","))
  if (withPeople.length) q.set("with", withPeople.join(","))
  return `/cases/${encodeURIComponent(caseId)}/phones/person?${q}`
}

export function momentHref(caseId: string, from: string, to: string, phones: string[] = []) {
  const q = new URLSearchParams({ from, to })
  if (phones.length) q.set("phones", phones.join(","))
  return `/cases/${encodeURIComponent(caseId)}/phones/moment?${q}`
}
