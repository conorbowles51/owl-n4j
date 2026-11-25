import { fetchAPI } from "@/lib/api-client"

/** Mentions in phone texts, checked against the case (backend routers/phone_mentions.py). */

export type MentionKind = "travel" | "meeting" | "at_place" | "home_away" | "plan" | "money" | "sent" | "deleted"
export type MentionOutcome = "contradicts" | "contradicts_weakly" | "fits_strongly" | "fits_weakly" | "cant_tell"
export type CheckVerdict = "fits" | "fits_weakly" | "contradicts" | "contradicts_weakly" | "context" | "nothing"

export interface MentionWhen { start: string; end: string; zone?: string; label?: string; words?: string | null; assumed?: string | null }
export interface MentionWhere { name: string; words?: string; located: boolean; lat?: number; lon?: number; radius_m?: number; routine?: string }

export interface Mention {
  id: string
  kind: MentionKind
  kind_label: string
  phrase: string
  start: number
  end: number
  body: string
  record_uid: string
  record_kind: string
  at: string
  phone: string
  phone_label: string | null
  copies: { record_uid: string; phone: string; phone_label: string | null }[]
  app: string | null
  from: string | null
  to: string[]
  who: string[]
  with: string[]
  when: MentionWhen | null
  where: MentionWhere | null
  how: string | null
  amounts_minor: number[]
  words: string[]
  reader: string
  state: "read" | "corrected" | "confirmed" | "rejected"
  read_by: string | null
  corrected_fields: string[]
  original: Record<string, unknown> | null
  decided_by: string | null
  decided_at: string | null
  outcome: MentionOutcome | null
  outcome_label: string
  basis: string | null
  why: string | null
  checked_at: string | null
}

export interface MentionCheck {
  source: string
  source_label: string
  verdict: CheckVerdict
  verdict_label: string
  text: string
  note: string
  refs: { ref: string; label: string }[]
  refs_total: number
  strong: boolean
}

export interface MentionDetail extends Mention {
  checks: MentionCheck[]
  would_test: string[]
  window: { start: string; end: string; label?: string | null }
}

export interface RunView {
  id: string
  phone: string
  phone_label: string | null
  reader: string
  status: "running" | "done" | "failed" | "stopped"
  texts_total: number
  texts_read: number
  mentions_found: number
  model_calls: number
  cost_usd: number
  error: string | null
  started_by: string
  started_at: string | null
  finished_at: string | null
}

export interface NextStep {
  n: number
  title: string
  why: string
  action: "open_mention" | "filter" | "open_map"
  label: string
  primary?: boolean
  mention_id?: string
  kind?: MentionKind
  outcome?: string
  place?: string
}

export interface MentionList {
  counts: { kind: MentionKind; label: string; fits: number; against: number; unknown: number; total: number }[]
  total: number
  shown: number
  offset: number
  mentions: Mention[]
  phones: { phone: string; phone_label: string | null; texts: number; rules: RunView | null; model: RunView | null; outside_allowed: boolean }[]
  how: { kind: MentionKind; label: string; how: string }[]
  next_steps: NextStep[]
  read_by: string
}

export interface MentionMarkView {
  id: string
  kind: MentionKind
  kind_label: string
  start: number
  end: number
  phrase: string
  outcome: MentionOutcome | null
  outcome_label: string
  state: string
  read_by: string | null
}

const base = (caseId: string) => `/api/cases/${encodeURIComponent(caseId)}/phone-mentions`

export const mentionsAPI = {
  list: (caseId: string, q: { phones?: string[]; kind?: string | null; outcome?: string | null; limit?: number; offset?: number }) => {
    const p = new URLSearchParams()
    if (q.phones?.length) p.set("phones", q.phones.join(","))
    if (q.kind) p.set("kind", q.kind)
    if (q.outcome) p.set("outcome", q.outcome)
    p.set("limit", String(q.limit ?? 100))
    if (q.offset) p.set("offset", String(q.offset))
    return fetchAPI<MentionList>(`${base(caseId)}?${p}`, { read: true })
  },
  detail: (caseId: string, id: string) => fetchAPI<MentionDetail>(`${base(caseId)}/${encodeURIComponent(id)}`, { read: true }),
  marks: (caseId: string, records: string[]) =>
    fetchAPI<{ marks: Record<string, MentionMarkView[]> }>(`${base(caseId)}/marks?records=${encodeURIComponent(records.join(","))}`, { read: true }),
  start: (caseId: string, phone: string, reader: "rules" | "model") =>
    fetchAPI<RunView>(`${base(caseId)}/runs`, { method: "POST", body: { phone, reader } }),
  decide: (caseId: string, id: string, body: { action: "correct" | "confirm" | "reject" | "restore"; values?: Record<string, unknown>; reason?: string }) =>
    fetchAPI<MentionDetail>(`${base(caseId)}/${encodeURIComponent(id)}/decision`, { method: "POST", body }),
  recheck: (caseId: string, id: string) => fetchAPI<MentionDetail>(`${base(caseId)}/${encodeURIComponent(id)}/check`, { method: "POST" }),
}

/** Where a cited record opens. */
export function refPath(caseId: string, ref: string): string | null {
  const c = `/cases/${encodeURIComponent(caseId)}`
  const [kind, id] = [ref.slice(0, ref.indexOf(":")), ref.slice(ref.indexOf(":") + 1)]
  if (kind === "phone_record") return `${c}/records/${encodeURIComponent(id)}`
  if (kind === "financial_transaction") return `${c}/financial?${new URLSearchParams({ view: "transactions", payment: id })}`
  if (kind === "evidence_file") return `${c}/evidence?file=${encodeURIComponent(id)}`
  return null
}
