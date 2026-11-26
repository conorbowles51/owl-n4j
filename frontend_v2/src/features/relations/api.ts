import { fetchAPI } from "@/lib/api-client"
import type { GroupInput, ItemInput } from "@/features/theory/api"
import type { Corroboration } from "@/features/corroborate/result-types"

/**
 * Corroborate (lx-overlaps; backend routers/relation_queries.py): items from any screen are saved as one
 * group and the link analysis runs on it. The records show what occurs together, never why.
 */
export type Strength = "strong" | "moderate" | "weak" | "faint"

export interface RelationMember {
  type: string
  id: string
  label?: string
  quote?: string
}

export interface RelationItem {
  ref: string
  type: string
  id: string
  label: string
  at: string | null
  /** "day": a date with no time of day, shown as a date only. */
  precision?: "day"
  state?: string
}

export interface Candidate {
  kind: string
  members: string[]
  key: string
  strength: Strength
  reasons: string[]
  chance: { words: string; reading: string; share_of_days: number | null }
  detail?: Record<string, unknown>
}

export interface NoLink {
  members: string[]
  analyses: string[]
  searched: string[]
  says: string
  out_of_reach: string[]
}

export interface RelationResult {
  says: string
  items: RelationItem[]
  candidates: Candidate[]
  no_links: NoLink[]
  analyses: { id: string; title: string; pairs: number; found: number; note?: string; existing: string | null }[]
  out_of_reach: { analysis: string; reason: string }[]
  paging?: { candidates: { total: number; shown: number }; no_links: { total: number; shown: number }; page: number }
  counts: { items: number; pairs: number; candidates: number; no_links: number; by_strength: Record<Strength, number> }
  seconds: number
  corroboration?: Corroboration
}

export interface Hypothesis {
  id: number
  kind: string
  statement: string
  predicts: string
  for: { cite: string; text: string }[]
  against: { cite: string; text: string }[]
  distinguishing_record: string
  search: string
  accepted: { relationship: string; by: string; entry_id: string } | null
}

export interface RelationRun {
  id: string
  selection_id: string
  status: "queued" | "running" | "done" | "failed"
  step: string
  progress: Record<string, number>
  error: string | null
  result?: RelationResult | null
  hypotheses: { model: string; status: string; no_links: string; items: Hypothesis[] } | null
}

export interface LaneEvent {
  n: number
  ref: string
  kind: string
  kind_words: string
  at: string
  day_only: boolean
  text: string
  with: string[]
  copies?: number
}

export interface StoryLanes {
  instance: { id: string; label: string }
  lanes: { person: string; label: string; events: LaneEvent[] }[]
  events: number
  cited: number
  folded_copies?: number
  not_laid_out: { ref: string; why: string }[]
}

export interface TrailStep {
  n: number
  selection_id: string
  created_at: string | null
  members: number
  added: { type: string; id: string; label?: string }[]
  added_count: number
  level: { run_id: string; key: string | null; name: string | null; sentence?: string } | null
  level_moved: "raised" | "lowered" | "unchanged" | null
  adds_nothing: boolean
}

export interface TrailResult {
  steps: TrailStep[]
  current: string
}

export interface RelationQuery {
  group: { id: string; member_count: number; left_out: number; members: RelationMember[]; created_at: string }
  run: RelationRun | null
}

const base = (caseId: string) => `/api/cases/${encodeURIComponent(caseId)}`

export const relationAPI = {
  create: (caseId: string, body: { members: RelationMember[]; extends?: string; surface?: string; question?: Record<string, unknown> }) =>
    fetchAPI<{ group: { id: string; member_count: number; left_out: number }; run: RelationRun | null }>(
      `${base(caseId)}/relation-queries`,
      { method: "POST", body: { ...body, run: true } },
    ),
  get: (caseId: string, selectionId: string) => fetchAPI<RelationQuery>(`${base(caseId)}/relation-queries/${encodeURIComponent(selectionId)}`),
  rerun: (caseId: string, selectionId: string) =>
    fetchAPI<RelationRun>(`${base(caseId)}/relation-queries/${encodeURIComponent(selectionId)}/runs`, { method: "POST" }),
  rows: <T,>(caseId: string, runId: string, section: "candidates" | "no_links", offset: number) =>
    fetchAPI<{ total: number; returned: number; next_offset: number | null; rows: T[] }>(
      `${base(caseId)}/relation-runs/${encodeURIComponent(runId)}/rows?section=${section}&offset=${offset}`),
  lanes: (caseId: string, runId: string, instance: string) =>
    fetchAPI<StoryLanes>(`${base(caseId)}/relation-runs/${encodeURIComponent(runId)}/lanes?instance=${encodeURIComponent(instance)}`),
  trail: (caseId: string, selectionId: string) =>
    fetchAPI<TrailResult>(`${base(caseId)}/relation-queries/${encodeURIComponent(selectionId)}/trail`),
  accept: (caseId: string, runId: string, n: number, entryId: string, relationship: "supports" | "contradicts") =>
    fetchAPI<{ added_link_ids: string[] }>(`${base(caseId)}/relation-runs/${encodeURIComponent(runId)}/hypotheses/${n}:accept`, {
      method: "POST",
      body: { entry_id: entryId, relationship },
    }),
}

/** Member types the analysis reads. Anything else is named to the person, never dropped silently. */
const TYPE_MAP: Record<string, string> = {
  graph_entity: "graph_entity", financial_transaction: "financial_transaction", financial_account: "financial_account",
  financial_party: "financial_party", evidence: "evidence", timeline_event: "timeline_event", phone_record: "phone_record",
  entry: "entry", evidence_passage: "evidence_passage", place: "place",
}

/** What Corroborate cannot read yet, in words a person uses (never the type's internal name). */
export const SKIPPED_WORDS: Record<string, [string, string]> = {
  phone_extraction: ["a whole phone", "whole phones"], phone_file: ["a phone file", "phone files"],
  phone_thread: ["a whole conversation", "whole conversations"], phone_identity: ["a phone contact", "phone contacts"],
  phone_analysis: ["a phone analysis", "phone analyses"], phone_selection: ["a saved phone selection", "saved phone selections"],
  phone_view: ["a saved phone view", "saved phone views"], interview: ["an interview", "interviews"],
  agent_answer: ["an assistant answer", "assistant answers"], dossier: ["a dossier", "dossiers"],
  statement_check: ["a statement check", "statement checks"], history_step: ["a step", "steps"],
  agent_artifact: ["a piece of assistant work", "pieces of assistant work"], task: ["a task", "tasks"],
  deadline: ["a deadline", "deadlines"], witness: ["a witness", "witnesses"],
  document_date: ["a dated line in a document", "dated lines in documents"],
}

export function skippedNoun(type: string, count: number): string {
  const w = SKIPPED_WORDS[type]
  if (w) return count === 1 ? w[0] : `${count.toLocaleString("en-US")} ${w[1]}`
  return count === 1 ? "an item of another kind" : `${count.toLocaleString("en-US")} items of another kind`
}

/** The sentence for chosen items Corroborate cannot read: what they are, and what to choose instead. */
export function skippedWords(skipped: { type: string; count: number }[], nothingElse = false): string {
  const list = skipped.map((s) => skippedNoun(s.type, s.count)).join(", ")
  const whole = skipped.some((s) => s.type === "phone_extraction" || s.type === "phone_thread")
  const instead = whole ? " Choose messages or other records on the phone instead, or open the phone on the Phones page." : ""
  return nothingElse
    ? `Corroborate reads records, people, payments and passages, not ${list}.${instead}`
    : `Corroborate cannot read ${list} yet; the rest of what you chose is asked about.${instead}`
}

export interface Converted {
  members: RelationMember[]
  skipped: { type: string; count: number }[]
}

export function toMembers(items?: ItemInput[], group?: GroupInput): Converted {
  const raw: { type: string; id: string; label?: string }[] = group
    ? group.members.map((m) => ({ type: m.type, id: m.id, label: m.label }))
    : (items ?? []).map((i) => ({ type: i.target_type, id: i.target_id, label: i.target_label }))
  const members: RelationMember[] = []
  const skipped = new Map<string, number>()
  for (const r of raw) {
    const type = TYPE_MAP[r.type]
    if (type) members.push({ type, id: r.id, ...(r.label ? { label: r.label } : {}) })
    else skipped.set(r.type, (skipped.get(r.type) ?? 0) + 1)
  }
  return { members, skipped: [...skipped].map(([type, count]) => ({ type, count })) }
}

/** The look in progress in this browser, so a payment, a passage, a phone meeting and a graph entity form one group. */
const KEY = (caseId: string) => `loupeRelationQuery:${caseId}`
export function currentQuery(caseId: string): { id: string; count: number } | null {
  try {
    const v = JSON.parse(localStorage.getItem(KEY(caseId)) ?? "null")
    return v && typeof v.id === "string" ? v : null
  } catch {
    return null
  }
}
export function setCurrentQuery(caseId: string, value: { id: string; count: number } | null) {
  try {
    if (value) localStorage.setItem(KEY(caseId), JSON.stringify(value))
    else localStorage.removeItem(KEY(caseId))
  } catch {
    /* storage may be blocked; the tray then starts fresh each time */
  }
  window.dispatchEvent(new Event("loupe-relation-query"))
}

export function runIsWorking(run: RelationRun | null | undefined): boolean {
  return !run || run.status === "queued" || run.status === "running"
}

export async function downloadRelationReport(caseId: string, runId: string): Promise<string> {
  const response = await fetch(`/api/cases/${encodeURIComponent(caseId)}/relation-runs/${encodeURIComponent(runId)}/report`, {
    method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include", body: JSON.stringify({ privilege_marking: "unmarked" }),
  })
  if (!response.ok) {
    const detail = await response.json().then((b) => b?.detail).catch(() => null)
    throw new Error(typeof detail === "string" ? detail : `Report not produced (${response.status})`)
  }
  const url = URL.createObjectURL(await response.blob())
  const a = document.createElement("a")
  a.href = url
  a.download = "link-analysis.pdf"
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  return "link-analysis.pdf"
}

