import { fetchAPI } from "@/lib/api-client"
import type { WorkspaceLinkType } from "@/generated/link-types"

/**
 * Everything in a case can be added to a theory, singly or as a group, and each addition explains itself
 * (lx-theorybuild; backend routers/theory_additions.py). An addition knows its members, why it was chosen and where
 * from, and carries a narrative written by a person or inferred by the model (a model reading, labelled as such
 * until a person confirms it).
 */
export type Surface =
  | "graph" | "significant" | "timeline" | "financial" | "evidence" | "passage" | "interview" | "agent" | "phone"
  | "map" | "search" | "workspace" | "history"

export type GroupType =
  | "graph_selection" | "significant_set" | "timeline_range" | "financial_selection" | "evidence_selection" | "map_selection" | "step_trail"

export const SURFACE_WORDS: Record<Surface, string> = {
  graph: "the graph",
  significant: "the Significant layer",
  timeline: "the timeline",
  financial: "the ledger",
  evidence: "the evidence files",
  passage: "a document's text",
  interview: "an interview",
  agent: "the case agent",
  phone: "the phone viewer",
  map: "the map",
  search: "search",
  workspace: "Workspace",
  history: "your step history",
}

export interface ItemInput {
  target_type: WorkspaceLinkType
  target_id: string
  target_label?: string
  source_anchor?: Record<string, unknown>
}

export interface GroupMember {
  type: "graph_entity" | "financial_transaction" | "financial_account" | "financial_party" | "evidence" | "timeline_event" | "phone_record" | "entry" | "history_step"
  id: string
  label?: string
}

export interface GroupInput {
  group_type: GroupType
  members: GroupMember[]
  /** How it was chosen: {filter}, {range}, {query}, {snapshot}, {area}, {selection} ... */
  how: Record<string, unknown>
  /** The person's words for the choice, e.g. "payments under 100 in March". */
  words: string
}

export interface AdditionInput {
  surface: Surface
  why?: string
  items?: ItemInput[]
  group?: GroupInput
  narrative?: string
  relationship?: "unclassified" | "supports" | "contradicts" | "context"
}

export interface AdditionResult {
  entry_id: string
  version: number
  added: number
  skipped: number
  added_link_ids: string[]
  group: { id: string; member_count: number; left_out: number; left_out_examples: string[]; label: string } | null
  title?: string
}

export interface Citation {
  mark: string
  ref: string
  label: string
}

export interface Narrative {
  id: string
  link_id: string | null
  text: string
  origin: "person" | "agent"
  model: string | null
  /** "Model reading · <model> · not confirmed" / "... · confirmed by <name>" / "Written by <name>". */
  words: string
  written_by: string | null
  asked_by: string | null
  citations: Citation[]
  basis: { read?: number; of?: number; invalid_citations?: number }
  replaces_id: string | null
  confirmed_by: string | null
  confirmed_at: string | null
  created_at: string | null
}

export interface Addition {
  link_id: string
  target_type: string
  target_id: string
  label: string
  relationship: string
  kind: "single" | "group"
  surface: Surface | null
  why: string | null
  how: Record<string, unknown> | null
  member_count: number | null
  left_out: number | null
  origin: "person" | "agent"
  model: string | null
  model_reading: boolean
  added_by: string | null
  accepted_by: string | null
  added_at: string | null
  source_anchor: Record<string, unknown>
  narrative: Narrative | null
  narrative_versions: number
}

export interface TheoryReading {
  entry: { id: string; entry_type: string; title: string | null; body: string; version: number }
  additions: Addition[]
  fit: Narrative | null
  fit_versions: number
}

export interface Member {
  ref: string
  type: string
  id: string
  label: string
  text: string
  state: "present" | "deleted" | "corrected" | "rejected" | "gone"
  date?: string | null
  amount_minor?: number
  currency?: string
  direction?: string
  corrected_by?: string
}

export interface LoupeView {
  entry: { id: string; title: string | null; entry_type: string }
  addition: Addition
  members: Member[]
  member_count: number
  members_shown: number
  group: { id: string; group_type: GroupType; surface: string; label: string; words: string; how: Record<string, unknown>; member_count: number; left_out: number; created_at: string | null } | null
  missing?: string
  history: Narrative[]
}

const base = (caseId: string) => `/api/workspace/${encodeURIComponent(caseId)}`

export const theoryAPI = {
  add: (caseId: string, entryId: string, body: AdditionInput) =>
    fetchAPI<AdditionResult>(`${base(caseId)}/entries/${encodeURIComponent(entryId)}/additions`, { method: "POST", body }),
  newTheory: (caseId: string, body: AdditionInput & { title: string; statement?: string }) =>
    fetchAPI<AdditionResult>(`${base(caseId)}/theories:from`, { method: "POST", body }),
  reading: (caseId: string, entryId: string) =>
    fetchAPI<TheoryReading>(`${base(caseId)}/entries/${encodeURIComponent(entryId)}/reading`),
  loupe: (caseId: string, entryId: string, linkId: string) =>
    fetchAPI<LoupeView>(`${base(caseId)}/entries/${encodeURIComponent(entryId)}/additions/${encodeURIComponent(linkId)}`),
  write: (caseId: string, entryId: string, linkId: string | null, text: string) =>
    fetchAPI<Narrative>(`${base(caseId)}/entries/${encodeURIComponent(entryId)}/narratives`, { method: "POST", body: { link_id: linkId, text } }),
  infer: (caseId: string, entryId: string, linkId: string | null) =>
    fetchAPI<Narrative>(`${base(caseId)}/entries/${encodeURIComponent(entryId)}/narratives:infer`, { method: "POST", body: { link_id: linkId } }),
  confirm: (caseId: string, entryId: string, narrativeId: string) =>
    fetchAPI<Narrative>(`${base(caseId)}/entries/${encodeURIComponent(entryId)}/narratives/${encodeURIComponent(narrativeId)}:confirm`, { method: "POST" }),
  undo: (caseId: string, entryId: string, linkIds: string[], version: number) =>
    fetchAPI<{ version: number }>(`${base(caseId)}/entries/${encodeURIComponent(entryId)}/links:remove`, {
      method: "POST",
      body: { link_ids: linkIds, expected_version: version },
    }),
}

/** "12 items from the ledger, chosen: payments under 100" or "1 item". */
export function choiceWords(count: number, surface: Surface, words?: string): string {
  const noun = count === 1 ? "item" : "items"
  return `${count.toLocaleString("en-US")} ${noun} from ${SURFACE_WORDS[surface]}${words ? `, chosen: ${words}` : ""}`
}

export interface TheoryMembers {
  entry: { id: string; title: string | null }
  members: (Member & { additions: string[] })[]
  member_count: number
  members_shown: number
  dated: number
  graph_keys: string[]
}

export const theoryMembersAPI = {
  get: (caseId: string, entryId: string) =>
    fetchAPI<TheoryMembers>(`${base(caseId)}/entries/${encodeURIComponent(entryId)}/members`),
}
