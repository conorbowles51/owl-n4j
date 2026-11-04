/**
 * Phone registry admin (02 sections 3.4 and 6.8): types, API calls and the words the page shows.
 * The registry is global, so every call is admin only (the server answers 403 to anyone else).
 */
import { fetchAPI } from "@/lib/api-client"

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
