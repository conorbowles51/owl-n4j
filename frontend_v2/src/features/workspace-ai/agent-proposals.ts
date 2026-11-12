import { fetchAPI } from "@/lib/api-client"

/** A case agent's drafted Workspace work, held for a person (backend routers/agent_proposals.py). */
export type AgentProposalKind =
  | "entry_draft"
  | "lead_card"
  | "timeline_addition"
  | "link_proposal"
  | "alternative_explanation"
  | "control_claim"
  | "payment_purpose"
  | "statement_claim"
  | "entity_proposal"
  | "glossary_term"
  | "counter_argument"
  | "dossier_change"

export interface LeadAlert {
  cite: string
  evidence_class?: string | null
  at?: string | null
  amount_minor?: number | null
  currency?: string | null
  direction?: string | null
  phone?: string | null
}

export interface AgentProposal {
  id: string
  case_id: string
  output_type: AgentProposalKind
  review_status: "pending_review" | "accepted" | "rejected"
  created_at?: string | null
  reviewed_at?: string | null
  accepted_targets?: { target_type: string; target_id: string; href?: string; label?: string }[]
  /** Why this kind sits where it does in the waiting list: what people did with earlier proposals of it. */
  order_reason?: string | null
  content: Record<string, unknown> & { citations?: string[] }
  citations: { source_id?: string; cite?: string; label?: string | null; status?: string }[]
  proposal: {
    kind: AgentProposalKind
    model?: string | null
    model_id?: string | null
    run_id?: string | null
    for_name?: string | null
    review?: { source_opened?: boolean; opened?: string[]; via?: string } | null
  }
}

export interface AgentProposalPage {
  items: AgentProposal[]
  total: number
  returned: number
  limit: number
  offset: number
  order_rule?: string | null
}

export interface GlossaryRow {
  txn: string
  ref?: string | null
  payment: string
  amount: string
  date: string
  proof_class: string
  paid_by: string
  paid_to: string
  days_from_mention: number
}

export interface GlossaryMention {
  rec: string
  kind: string
  at: string | null
  people: string[]
  rows: GlossaryRow[]
  rows_outside_window: number
  join_reason: string | null
}

export interface GlossaryTerm {
  id: string
  term: string
  meaning: string
  model_meaning: string | null
  meaning_changed: boolean
  speaker: string | null
  citations: string[]
  status: "confirmed" | "withdrawn"
  confirmed_by: string
  confirmed_at: string | null
  reading_words: string
  keyword_list_note?: string | null
  withdrawn_by: string | null
  withdrawn_reason: string | null
  mentions?: {
    total: number
    with_rows: number
    without_rows: number
    items: GlossaryMention[]
    join_rule: string
    search_limits: string[]
  }
}

export interface Glossary {
  total: number
  confirmed: number
  items: GlossaryTerm[]
  limitation: string
}

export interface RedCellResult {
  theory_id: string
  model: { provider: string; model_id: string }
  agent_model: { provider: string; model_id: string }
  facts: number
  names_neutralised: number
  returned: number
  recorded: number
  refused: { title: string | null; why: string }[]
}

export interface DisconfirmAbsence {
  kind: string
  what: string
  reason: string
  why?: string | null
  expectation?: string | null
  basis?: string
  tied?: boolean
}

/** One sweep of a theory across the whole case (backend services/agent/disconfirm.py). */
export interface DisconfirmSweep {
  id: string
  case_id?: string
  theory_id: string
  theory_title: string
  stage: "planning" | "planned" | "reading" | "done"
  step: string
  job_status: "queued" | "running" | "completed" | "failed" | "cancelled"
  progress: number
  error: string | null
  cancel_requested: boolean
  started_at: string | null
  completed_at: string | null
  model: { provider: string; model_id: string; others_configured: string[]; words: string }
  expectations: { id: string; claim: string; would_contradict: string }[]
  reads: {
    total: number
    done: number
    running: number
    pending: number
    failed: number
    items: number
    items_read: number
    failures: { id: string; expectation: string; error: string | null }[]
    seconds_per_read: number | null
    slowest_running_seconds: number | null
    slow: boolean
  }
  calls_stated: number | null
  time_left: { seconds: number; label: string } | null
  cost: { usd: number; tokens: number; calls: number }
  proposals: { id: string; title: string; expectation: string; strength: string; citations: number; folded?: number }[]
  refused: { title: string | null; expectation: string; why: string }[]
  repeats: { title: string; expectation: string }[]
  /** Findings of this sweep that stated one fact, folded into one proposal each, every citation kept. */
  fold?: {
    calls: number
    groups: number
    folded: number
    skipped: { id: string; why: string }[]
    not_folded?: { ids: string[]; why: string }[]
    error?: string | null
  } | null
  absences: { items: DisconfirmAbsence[]; not_checked: string[]; needs: number; limitation: string } | null
  outcome: {
    headline: string
    complete: boolean
    findings: number
    not_read: number
    absences: number
    not_support: string
    expectations: {
      id: string
      claim: string
      reads: number
      unread: number
      findings: number
      repeats: number
      searched: string[]
      out_of_reach: string[]
      sentence: string | null
    }[]
  }
}

export interface ProposalTally {
  total: number
  accepted: number
  rejected: number
  waiting: number
  precision: number | null
}

export interface DisconfirmState {
  sweep: DisconfirmSweep | null
  tally: { counter_arguments: ProposalTally; red_cell: ProposalTally }
  counter_arguments: (AgentProposal & {
    accepted_by: string | null
    model_text: string
    person_text: string | null
  })[]
}

export const AGENT_PROPOSAL_LABELS: Record<AgentProposalKind, string> = {
  entry_draft: "Drafted note or finding",
  lead_card: "Lead card",
  timeline_addition: "Timeline addition",
  link_proposal: "Link to an entry",
  alternative_explanation: "Alternative explanation (red cell)",
  control_claim: "Means to operate an account (phones)",
  payment_purpose: "Stated purpose of a payment (phones)",
  statement_claim: "Statement claim",
  entity_proposal: "Entity for the graph",
  glossary_term: "Code-word meaning",
  counter_argument: "Counter-argument (disconfirm sweep)",
  dossier_change: "Dossier changes",
}

const base = (caseId: string) => `/api/workspace/${encodeURIComponent(caseId)}/proposals`

export const agentProposalKeys = {
  all: (caseId: string) => ["agent-proposals", caseId] as const,
  glossary: (caseId: string) => ["agent-proposals", caseId, "glossary"] as const,
  list: (caseId: string, status: string) => ["agent-proposals", caseId, status] as const,
}

export function listAgentProposals(caseId: string, status = "pending_review", offset = 0) {
  return fetchAPI<AgentProposalPage>(`${base(caseId)}?status=${encodeURIComponent(status)}&limit=50&offset=${offset}`)
}

export function agentProposalOpened(caseId: string, id: string, citation: string) {
  return fetchAPI<{ opened: string[] }>(`${base(caseId)}/${id}/opened`, { method: "POST", body: { citation } })
}

export function fetchGlossary(caseId: string) {
  return fetchAPI<Glossary>(`/api/workspace/${encodeURIComponent(caseId)}/glossary`)
}

export function withdrawGlossaryTerm(caseId: string, id: string, reason: string) {
  return fetchAPI<GlossaryTerm>(`/api/workspace/${encodeURIComponent(caseId)}/glossary/${id}/withdraw`, { method: "POST", body: { reason } })
}

export function acceptAgentProposal(
  caseId: string,
  id: string,
  body: { due_at?: string | null; title?: string; body?: string; schedule?: string; meaning?: string } = {}
) {
  return fetchAPI<AgentProposal>(`${base(caseId)}/${id}/accept`, { method: "POST", body: { ...body, via: "ui" } })
}

export function rejectAgentProposal(caseId: string, id: string, reason: string) {
  return fetchAPI<AgentProposal>(`${base(caseId)}/${id}/reject`, { method: "POST", body: { reason } })
}

export function runRedCell(caseId: string, theoryId: string) {
  return fetchAPI<RedCellResult>(`${base(caseId)}/red-cell`, { method: "POST", body: { theory_id: theoryId } })
}

export function fetchDisconfirm(caseId: string, theoryId: string) {
  return fetchAPI<DisconfirmState>(`${base(caseId)}/disconfirm?theory_id=${encodeURIComponent(theoryId)}`)
}

export function planDisconfirm(caseId: string, theoryId: string) {
  return fetchAPI<DisconfirmSweep>(`${base(caseId)}/disconfirm`, { method: "POST", body: { theory_id: theoryId } })
}

export function startDisconfirm(caseId: string, sweepId: string, limit?: number) {
  return fetchAPI<DisconfirmSweep>(`${base(caseId)}/disconfirm/${sweepId}/start`, {
    method: "POST",
    body: limit ? { limit } : {},
  })
}

export function stopDisconfirm(caseId: string, sweepId: string) {
  return fetchAPI<DisconfirmSweep>(`${base(caseId)}/disconfirm/${sweepId}/stop`, { method: "POST" })
}

/** The red cell's alternatives for one theory, counted by what people decided (latest 100 in the case). */
export async function fetchTheoryAlternatives(caseId: string, theoryId: string) {
  const page = await fetchAPI<AgentProposalPage>(
    `${base(caseId)}?status=all&output_type=alternative_explanation&limit=100`
  )
  const mine = page.items.filter((item) => item.content.theory_id === theoryId)
  return {
    total: mine.length,
    accepted: mine.filter((item) => item.review_status === "accepted").length,
    rejected: mine.filter((item) => item.review_status === "rejected").length,
    waiting: mine.filter((item) => item.review_status === "pending_review").length,
    truncated: page.total > page.items.length,
  }
}

/** An alert's amount as printed, in its currency's own minor unit. Never added to another. */
export function alertAmount(alert: Pick<LeadAlert, "amount_minor" | "currency">) {
  if (alert.amount_minor == null || !alert.currency) return null
  try {
    const format = new Intl.NumberFormat("en-US", { style: "currency", currency: alert.currency })
    const digits = format.resolvedOptions().maximumFractionDigits ?? 2
    return format.format(alert.amount_minor / 10 ** digits)
  } catch {
    return `${alert.amount_minor} (minor units) ${alert.currency}`
  }
}
