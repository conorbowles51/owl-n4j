/**
 * Phone registry admin (02 sections 3.4 and 6.8): types, API calls and the words the page shows.
 * The registry is global, so every call is admin only (the server answers 403 to anyone else).
 */
import { ApiError, fetchAPI } from "@/lib/api-client"

export type FlagState = "open" | "acknowledged" | "mapping_needed" | "mapped" | "dismissed"
export type ProposalState = "draft" | "exported" | "rejected"
export type ProposalOrigin = "case_correction" | "ai_draft"

export interface FlagSubject {
  type?: string | null
  field?: string | null
  kind?: string | null
  value_type?: string | null
  child?: string | null
  set?: string | null
  value?: string | null
  element?: string | null
  attribute?: string | null
}

export interface LastEvent {
  to: string
  reason: string
  by: string | null
  at: string
}

export interface RegistryFlag {
  id: number
  flag_kind: string
  registry_table: string
  severity: string
  state: FlagState
  detail: Record<string, unknown>
  raised_at: string
  subject: FlagSubject
  raised_by: { extraction_id: string; case_id: string | null; case_title: string | null; label: string | null; link: string | null } | null
  last_event: LastEvent | null
}

export interface FlagPage {
  total: number
  limit: number
  offset: number
  counts: Record<FlagState, number>
  flags: RegistryFlag[]
}

export interface MappingProposal {
  id: string
  kind: string
  name: string
  origin: ProposalOrigin
  state: ProposalState
  created_at: string
  model: string | null
  case: { id: string; title: string } | null
  rule_id: string | null
  original: unknown
  correction: unknown
  correction_label: string | null
  decided_by: { name: string; email: string; reason: string; at: string | null } | null
  last_event: LastEvent | null
  file_path: string
}

export interface ProposalPage {
  total: number
  limit: number
  offset: number
  counts: Record<ProposalState, number>
  proposals: MappingProposal[]
}

export type DraftStatus = "queued" | "running" | "drafted" | "invalid" | "failed"

/** One AI draft run (02 6.8 step 2): the model's answer becomes an `ai_draft` proposal, `draft` when it is a valid
 * mapping and `rejected` with the reason when not; a run with no answer is `failed` with the reason. */
export interface DraftRun {
  id: string
  kind: string
  name: string
  status: DraftStatus
  provider: string | null
  model: string | null
  input_summary: Record<string, unknown>
  proposal_id: string | null
  error: string | null
  seconds: number | null
  prompt_tokens: number | null
  completion_tokens: number | null
  cost_usd: number | null
  requested_by: string | null
  created_at: string
  finished_at: string | null
}

export interface Draftable {
  name: string
  kind: "type" | "attribution"
  records_observed: number
}

export interface DraftRunPage {
  total: number
  runs: DraftRun[]
  draftable: { types: Draftable[]; named_sets: Draftable[]; total: number }
}

export const DRAFT_STATUS_WORDS: Record<DraftStatus, string> = {
  queued: "Waiting to start",
  running: "The model is drafting",
  drafted: "Drafted: waiting in Proposals",
  invalid: "Not a valid mapping: kept in Proposals as rejected",
  failed: "No draft: the model did not answer",
}

export function draftRunning(runs: DraftRun[] | undefined): boolean {
  return !!runs?.some((r) => r.status === "queued" || r.status === "running")
}

/** "deepseek-v4-pro · 2 min 14 s · $0.0123": who drafted it, how long it took and what it cost. */
export function draftRunFacts(r: Pick<DraftRun, "model" | "seconds" | "cost_usd">): string {
  const parts: string[] = []
  if (r.model) parts.push(r.model)
  if (r.seconds != null) {
    const m = Math.floor(r.seconds / 60)
    const sec = Math.round(r.seconds - m * 60)
    parts.push(m ? m + " min " + sec + " s" : sec + " s")
  }
  if (r.cost_usd != null) parts.push("$" + r.cost_usd.toFixed(4))
  return parts.join(" · ")
}

/** What a flag would be drafted for: a named set's flag drafts the set, any other the record type. */
export function draftTargetForFlag(flag: Pick<RegistryFlag, "subject">): string | null {
  const s = flag.subject ?? {}
  return s.set || s.type || null
}

/** Retry a failed read up to 3 times, but never a refusal: a non-admin sees the admin-only message at once. */
export function retryUnlessRefused(failures: number, err: unknown): boolean {
  if (err instanceof ApiError && (err.status === 401 || err.status === 403)) return false
  return failures < 3
}

export const FLAG_PAGE = 100
export const PROPOSAL_PAGE = 50

export const FLAG_STATE_WORDS: Record<FlagState, string> = {
  open: "Open",
  mapping_needed: "Waiting for a mapping",
  acknowledged: "Acknowledged",
  mapped: "Mapped",
  dismissed: "Dismissed",
}

export const PROPOSAL_STATE_WORDS: Record<ProposalState, string> = {
  draft: "Waiting",
  exported: "File downloaded",
  rejected: "Rejected",
}

export const ORIGIN_WORDS: Record<ProposalOrigin, string> = {
  case_correction: "Correction in a case",
  ai_draft: "AI draft",
}

const KIND_WORDS: Record<string, string> = {
  new_type: "New record type",
  new_field: "New field",
  new_value_type: "Field holds a new kind of value",
  new_set_value: "New value in a list",
  new_nesting: "New record inside another",
  new_attribute: "New attribute",
  set_overflow: "List has too many values to record",
  multi_value_field: "Field holds more than one value",
}

export function flagKindWords(kind: string): string {
  return KIND_WORDS[kind] ?? kind.replace(/_/g, " ")
}

/** What a flag is about, as one line: "Call · Direction (ModelDirections)", "ModelDirections: Sideways". */
export function flagSubjectWords(flag: Pick<RegistryFlag, "flag_kind" | "subject" | "detail">): string {
  const s = flag.subject ?? {}
  if (s.set) return s.value != null ? `${s.set}: ${s.value}` : s.set
  if (s.element) return `${s.element} · ${s.attribute ?? ""}`
  const parts = [s.type, s.field].filter(Boolean).join(" · ")
  if (s.child) return `${parts} → ${s.child}`
  if (flag.flag_kind === "new_value_type") {
    const prev = (flag.detail?.previous as string[] | undefined)?.join(", ")
    const now = flag.detail?.now as string | undefined
    return prev ? `${parts} (was ${prev}, now ${now ?? s.value_type ?? "?"})` : parts
  }
  return s.value_type && !["(none)", "(empty)"].includes(s.value_type) ? `${parts} (${s.value_type})` : parts
}

export type FlagAction = { to: Exclude<FlagState, "mapped">; label: string }

/** The transitions a person may make from each state (02 section 3.4); `mapped` is set only by a loaded mapping. */
export function flagActions(state: FlagState): FlagAction[] {
  const dismiss: FlagAction = { to: "dismissed", label: "Dismiss" }
  const reopen: FlagAction = { to: "open", label: "Reopen" }
  switch (state) {
    case "open":
      return [{ to: "acknowledged", label: "Acknowledge" }, { to: "mapping_needed", label: "Needs a mapping" }, dismiss]
    case "acknowledged":
      return [reopen, dismiss]
    case "dismissed":
      return [reopen]
    default:
      return [dismiss]
  }
}

/** "Showing 1 to 100 of 500": never a clipped list shown as whole. */
export function rangeWords(offset: number, shown: number, total: number): string {
  if (total === 0) return "None"
  if (shown === 0) return `None on this page of ${total.toLocaleString()}`
  return `Showing ${(offset + 1).toLocaleString()} to ${(offset + shown).toLocaleString()} of ${total.toLocaleString()}`
}

/** A reading as words: a field name, a role, or a timestamp meaning's sentence. */
export function readingWords(v: unknown): string {
  if (v == null) return "Not set"
  if (typeof v === "string") return v
  if (Array.isArray(v)) return v.length ? v.map(readingWords).join(", ") : "None"
  if (typeof v === "object") {
    const o = v as Record<string, unknown>
    if (typeof o.meaning === "string") return o.meaning
    if (typeof o.semantics === "string") return o.semantics.replace(/_/g, " ")
    return JSON.stringify(v)
  }
  return String(v)
}

function qs(params: Record<string, string | number | undefined>) {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") q.set(k, String(v))
  return q.toString()
}

export const registryApi = {
  flags: (state: FlagState | undefined, offset: number) =>
    fetchAPI<FlagPage>(`/api/phones/registry/flags?${qs({ state, limit: FLAG_PAGE, offset })}`),
  transition: (id: number, to: FlagAction["to"], reason: string) =>
    fetchAPI<{ flag_id: number; from: string; to: string }>(`/api/phones/registry/flags/${id}/transition`, {
      method: "POST",
      body: { to, reason },
    }),
  proposals: (state: ProposalState | undefined, origin: ProposalOrigin | undefined, offset: number) =>
    fetchAPI<ProposalPage>(`/api/phones/registry/proposals?${qs({ state, origin, limit: PROPOSAL_PAGE, offset })}`),
  reject: (id: string, reason: string) =>
    fetchAPI<{ proposal_id: string; to: string }>(`/api/phones/registry/proposals/${id}/reject`, {
      method: "POST",
      body: { reason },
    }),
  draftRuns: () => fetchAPI<DraftRunPage>("/api/phones/registry/mapping-drafts?limit=20"),
  startDraft: (typeName: string) =>
    fetchAPI<DraftRun>("/api/phones/registry/mapping-drafts", { method: "POST", body: { type_name: typeName } }),
  exportFile: (id: string) => fetchAPI<Record<string, unknown>>(`/api/phones/registry/proposals/${id}/export`),
}

/** Save the mapping file in the browser (works over plain http: no clipboard or file-system API). */
export function saveFile(name: string, content: Record<string, unknown>) {
  const blob = new Blob([JSON.stringify(content, null, 1) + "\n"], { type: "application/json" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
