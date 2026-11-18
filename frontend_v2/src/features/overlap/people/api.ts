import { fetchAPI } from "@/lib/api-client"
import type { RelationMember } from "@/features/relations/api"

/** Backend routers/corroborate_overlaps.py (services/corroborate/overlaps.py): every pair against every kind. */
export type OverlapKind = "contact" | "through_others" | "groups" | "shared" | "place" | "access" | "money" | "documents"

export interface OverlapRecord {
  ref: string
  kind: string
  at: string | null
  day_only: boolean
  from: string | null
  body: string | null
  copies: number
  deleted: boolean
  amount_minor: number | null
  app: string | null
}

export interface GoBetween { key: string; label: string; with_a: number; with_b: number; route_days: number }
export interface PairDocument { file_id: string; file: string; pages: Record<string, number[]>; by: Record<string, string> }

export interface KindResult {
  count: number
  words: string
  records?: OverlapRecord[]
  go_betweens?: GoBetween[]
  groups?: { title: string; app: string | null; records: number; members: string[] }[]
  documents?: PairDocument[]
  days?: string[]
  searched?: boolean
  model_reading?: boolean
}

export interface LeadLevel { key: string; name: string; sentence?: string }
export interface PairLead {
  id: string
  title?: string
  level?: LeadLevel
  origin?: string
  state?: string
  searched?: unknown
  raises?: unknown
  lowers?: unknown
}

export interface Pair {
  a: string
  b: string
  label: string
  kinds: Record<OverlapKind, KindResult>
  kinds_found: OverlapKind[]
  direct: boolean
  records: number
  state: "not_weighed" | "nothing" | "weighed" | "no_link"
  level?: LeadLevel
  leads?: PairLead[]
}

export interface OverlapPerson {
  key: string
  label: string
  full_label: string
  dossier_id: string | null
  phones: number
  records: number
  position_days: number
  identifiers: string[]
}

export interface PatternStep {
  at: string
  local: string
  with: string | null
  body: string | null
  ref: string
  reply: { local: string; body: string | null; ref: string } | null
}

export interface GoBetweenPanel {
  key: string
  label: string
  reaches: string[]
  people: { key: string; label: string; contacts: number; place_days: number; position_days: number }[]
  records: number
  position_days: number
  pattern: { times: number; of: number; steps: PatternStep[]; zone: string; days: string[] } | null
}

export interface GraphSquare {
  people: string[]
  documents: { file_id: string; file: string; people: { key: string; by: string; pages: number[] }[] }[]
}

export interface Overlaps {
  schema: string
  zone: string
  people: OverlapPerson[]
  left_out: string[]
  pairs: Pair[]
  kinds: { key: OverlapKind; name: string; searched: string }[]
  worth_a_look: { a: string; b: string; label: string; reasons: string[]; words: string[] }[]
  documents: { read: number; naming_two_phone_owners: number }
  go_betweens: Record<string, GoBetweenPanel>
  graph: {
    nodes: OverlapPerson[]
    lines: { a: string; b: string; records: number }[]
    dashed: { a: string; b: string; via: string; via_label: string; money: number }[]
    squares: GraphSquare[]
    documents: { read: number; naming_two_phone_owners: number }
  }
  notes: string[]
  read_at?: string
  seconds: number
}

/** A case too large to read at once: said so, with its size and the limit, never shown as an empty grid. */
export interface OverlapsRefused { schema: string; refused: true; records: number; limit: number; words: string }

export function isRefused(x: Overlaps | OverlapsRefused): x is OverlapsRefused {
  return (x as OverlapsRefused).refused === true
}

export const overlapsAPI = {
  get: (caseId: string, fresh = false) =>
    fetchAPI<Overlaps | OverlapsRefused>(`/api/cases/${caseId}/corroborate/overlaps${fresh ? "?fresh=true" : ""}`),
}

/** A person of the grid as a Corroborate member: a dossier, or the phone of a number with no owner name. */
export function memberOf(p: OverlapPerson): RelationMember {
  if (p.dossier_id) return { type: "person", id: p.dossier_id, label: p.label }
  return { type: "phone", id: p.key.replace(/^phone:/, ""), label: p.label }
}
