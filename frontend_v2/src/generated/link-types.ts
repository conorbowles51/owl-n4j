// Generated from backend/postgres/link_types.py by `python3 -m scripts.generate_link_types`.
// Do not edit by hand: change the registry and run the generator.

export const PHONE_LINK_TYPES = [
  "phone_record",
  "phone_file",
  "phone_thread",
  "phone_identity",
  "phone_extraction",
  "phone_analysis",
  "phone_selection",
  "phone_view",
  "statement_check",
] as const
export type PhoneLinkType = (typeof PHONE_LINK_TYPES)[number]

export const WORKSPACE_LINK_TYPES = [
  "evidence",
  "graph_entity",
  "dossier",
  "entry",
  "task",
  "deadline",
  "timeline_event",
  "agent_artifact",
  "witness",
  "phone_record",
  "phone_file",
  "phone_thread",
  "phone_identity",
  "phone_extraction",
  "phone_analysis",
  "phone_selection",
  "phone_view",
  "statement_check",
  "financial_account",
  "financial_party",
  "financial_transaction",
  "evidence_passage",
  "graph_selection",
  "significant_set",
  "timeline_range",
  "financial_selection",
  "evidence_selection",
  "map_selection",
  "step_trail",
  "agent_answer",
  "interview",
] as const
export type WorkspaceLinkType = (typeof WORKSPACE_LINK_TYPES)[number]

export const DOSSIER_LINK_TYPES = [
  "entry",
  "task",
  "evidence",
  "deadline",
  "timeline_event",
  "agent_artifact",
  "graph_entity",
  "dossier",
  "phone_record",
  "phone_file",
  "phone_thread",
  "phone_identity",
  "phone_extraction",
  "phone_analysis",
  "phone_selection",
  "statement_check",
  "financial_account",
  "financial_party",
  "financial_transaction",
  "evidence_passage",
] as const
export type DossierLinkType = (typeof DOSSIER_LINK_TYPES)[number]

export const NOTEBOOK_LINK_TYPES = [
  "entity",
  "evidence",
  "document",
  "timeline_event",
  "agent_artifact",
  "phone_record",
  "phone_file",
  "phone_thread",
  "phone_identity",
  "phone_extraction",
  "phone_analysis",
  "phone_selection",
  "phone_view",
  "statement_check",
  "evidence_passage",
] as const
export type NotebookLinkType = (typeof NOTEBOOK_LINK_TYPES)[number]

export const TASK_LINK_TYPES = [
  "dossier",
  "entry",
  "evidence",
  "phone_record",
  "phone_file",
  "phone_thread",
  "phone_identity",
  "phone_extraction",
  "phone_analysis",
  "phone_selection",
  "phone_view",
  "statement_check",
] as const
export type TaskLinkType = (typeof TASK_LINK_TYPES)[number]

export const INTERVIEW_EVIDENCE_LINK_TYPES = [
  "evidence",
  "phone_record",
  "phone_file",
  "phone_analysis",
  "statement_check",
] as const
export type InterviewEvidenceLinkType = (typeof INTERVIEW_EVIDENCE_LINK_TYPES)[number]

export const LINK_TYPE_WORDS: Record<string, string> = {
  evidence: "Evidence file",
  graph_entity: "Graph item",
  dossier: "Dossier",
  entry: "Workspace entry",
  task: "Task",
  deadline: "Deadline",
  timeline_event: "Timeline event",
  agent_artifact: "Agent output",
  witness: "Witness",
  phone_record: "Phone record",
  phone_file: "Phone file",
  phone_thread: "Phone conversation",
  phone_identity: "Phone identity",
  phone_extraction: "Phone extraction",
  phone_analysis: "Phone analysis",
  phone_selection: "Phone collection",
  phone_view: "Saved phone view",
  statement_check: "Statement check",
  financial_account: "Bank account",
  financial_party: "Payer or payee",
  financial_transaction: "Payment",
  evidence_passage: "Quote",
  graph_selection: "Graph selection",
  significant_set: "Significant set",
  timeline_range: "Timeline range",
  financial_selection: "Ledger selection",
  evidence_selection: "Evidence selection",
  map_selection: "Map area",
  step_trail: "Step trail",
  agent_answer: "Agent answer",
  interview: "Interview",
  entity: "Graph item",
  document: "Evidence file",
}

/** The plain name of a link type; an unknown type reads "Linked item", never its raw name. */
export function linkTypeWords(value: string | null | undefined): string {
  return (value && LINK_TYPE_WORDS[value]) || "Linked item"
}

export function isPhoneLinkType(value: string): value is PhoneLinkType {
  return (PHONE_LINK_TYPES as readonly string[]).includes(value)
}
