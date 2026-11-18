import { fetchAPI } from "@/lib/api-client"

/** Backend routers/leads.py: the one list of leads (lx-leads). A lead is Loupe's reading until a person confirms it. */
export type LevelKey = "strong" | "probable" | "possible" | "cant_tell" | "coincidence" | "no_link_found" | "set_aside"

export interface Lead {
  id: string
  origin: "found_by_loupe" | "asked" | "agent"
  origin_words: string
  state: "new" | "looking" | "in_theory" | "not_relevant"
  state_words: string
  state_history: { at: string; from: string | null; to: string; by_name?: string | null; why?: string | null }[]
  level: { key: LevelKey; name: string; sentence?: string; rule?: string }
  title: string
  summary: string
  read: { title: string; summary: string; by: string; words: string }
  corrections: { field: string; original: string; value: string; by_name: string; at: string }[]
  people: { key: string; label: string }[]
  period: { from?: string; to?: string }
  kinds: string[]
  kind_words: string[]
  record_refs: string[]
  raises: string[]
  lowers: string[]
  searched: { records_read?: Record<string, number>; kinds_checked?: string[]; instances?: number; people?: number }
  detail: Record<string, unknown> & { refs_total?: number; family?: string }
  selection_id: string
  run_id: string | null
  unseen: boolean
  watching: boolean
  finding_id: string | null
  confirmed: { by: string; at: string } | null
  created_at: string | null
  checked_at: string | null
}

export interface FinderState {
  status: "never" | "queued" | "running" | "done" | "failed"
  step?: string
  words?: string
  counts?: Record<string, unknown>
  error?: string | null
  started_at?: string | null
  finished_at?: string | null
  /** The case's material changed since this run: look again to bring the leads up to date. */
  new_material?: boolean
}

export interface LeadFilter {
  records?: string[]
  people?: string[]
  from?: string
  to?: string
}

const base = (caseId: string) => `/api/cases/${encodeURIComponent(caseId)}/leads`

function query(f?: LeadFilter): string {
  if (!f) return ""
  const q = new URLSearchParams()
  if (f.records?.length) q.set("records", f.records.join(","))
  if (f.people?.length) q.set("people", f.people.join(","))
  if (f.from) q.set("from", f.from)
  if (f.to) q.set("to", f.to)
  const s = q.toString()
  return s ? `?${s}` : ""
}

export const leadsAPI = {
  list: (caseId: string, f?: LeadFilter) => fetchAPI<{ leads: Lead[]; total: number; finder: FinderState }>(`${base(caseId)}${query(f)}`),
  /** "Leads already here": the filter in the body, since a thread's records do not fit in an address. */
  here: (caseId: string, f: LeadFilter) =>
    fetchAPI<{ leads: Lead[]; total: number; finder: FinderState }>(`${base(caseId)}:here`, {
      method: "POST",
      body: { records: f.records ?? [], people: f.people ?? [], ...(f.from ? { from: f.from } : {}), ...(f.to ? { to: f.to } : {}) },
    }),
  count: (caseId: string) => fetchAPI<{ count: number; new: number }>(`${base(caseId)}/count`),
  seen: (caseId: string, id: string) => fetchAPI<Lead>(`${base(caseId)}/${encodeURIComponent(id)}:seen`, { method: "POST" }),
  state: (caseId: string, id: string, state: "new" | "looking" | "not_relevant", why?: string) =>
    fetchAPI<Lead>(`${base(caseId)}/${encodeURIComponent(id)}:state`, { method: "POST", body: { state, ...(why ? { why } : {}) } }),
  correct: (caseId: string, id: string, field: "title" | "summary", value: string) =>
    fetchAPI<Lead>(`${base(caseId)}/${encodeURIComponent(id)}:correct`, { method: "POST", body: { field, value } }),
  confirm: (caseId: string, id: string, theoryId: string) =>
    fetchAPI<Lead>(`${base(caseId)}/${encodeURIComponent(id)}:confirm`, { method: "POST", body: { theory_id: theoryId } }),
  find: (caseId: string) => fetchAPI<FinderState>(`${base(caseId)}:find`, { method: "POST" }),
}

export const LEVEL_DOT: Record<LevelKey, string> = {
  strong: "bg-red-700",
  probable: "bg-orange-500",
  possible: "bg-amber-400",
  cant_tell: "border border-slate-400 bg-transparent",
  coincidence: "bg-slate-400",
  no_link_found: "bg-slate-300",
  set_aside: "bg-slate-200",
}

/** The kind filters of the Leads page, in the design's words. */
export const KIND_FILTERS: { key: string; label: string; kinds: string[] }[] = [
  { key: "contact", label: "Contact", kinds: ["contact", "sequence"] },
  { key: "together", label: "Together", kinds: ["together"] },
  { key: "money", label: "Money", kinds: ["money"] },
  { key: "words", label: "Words and files", kinds: ["shared_content"] },
  { key: "access", label: "Access logs", kinds: ["access"] },
  { key: "silence", label: "Silence and deletion", kinds: ["absence"] },
]

const READ_WORDS: Record<string, [string, string]> = {
  message: ["message", "messages"], call: ["call", "calls"], email: ["e-mail", "e-mails"],
  position: ["phone position", "phone positions"], payment: ["bank row", "bank rows"],
  payment_alert: ["payment alert", "payment alerts"], doc_row: ["document line", "document lines"],
  media_position: ["photo place", "photo places"],
}

/** "Searched: 683 messages, 694 phone positions, ..." in plain words. */
export function searchedWords(s: Lead["searched"]): string {
  const parts = Object.entries(s.records_read ?? {})
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${n.toLocaleString()} ${(READ_WORDS[k] ?? [k, k])[n === 1 ? 0 : 1]}`)
  const nights = s.instances ? `${s.instances} nights and days compared` : ""
  return [parts.join(", "), nights].filter(Boolean).join("; ")
}
