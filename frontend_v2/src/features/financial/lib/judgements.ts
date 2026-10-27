import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"

/** A value the processor chose that the page does not print outright, or a choice between two readings. */
export const judgementSchema = z.object({
  id: z.string(),
  case_id: z.string(),
  subject_type: z.string(),
  subject_id: z.string(),
  source_document_id: z.string().nullable(),
  statement_period_id: z.string().nullable(),
  evidence_file_id: z.string().nullable(),
  filename: z.string().nullable().optional(),
  rule_id: z.string(),
  rule_label: z.string(),
  rule_source: z.string(),
  target_key: z.string(),
  origin: z.enum(["processor", "agent"]),
  strength: z.enum(["proved", "inferred"]),
  summary: z.string(),
  page: z.number().nullable().optional(),
  status: z.enum(["open", "confirmed", "corrected"]),
  resolved_by: z.string().nullable(),
  resolved_at: z.string().nullable(),
  resolution_reason: z.string().nullable(),
  adjudication_id: z.string().nullable(),
})
export type Judgement = z.infer<typeof judgementSchema>

const listSchema = z.object({ items: z.array(judgementSchema) })
const tally = z.record(z.string(), z.union([z.number(), z.string(), z.null()]))
const countsSchema = z.object({
  case: tally,
  statements: z.record(z.string(), tally),
  rules: z.array(
    z.object({ rule_id: z.string(), label: z.string(), total: z.number() }).passthrough()
  ),
})
const ruleRecord = z.object({
  rule_id: z.string(),
  label: z.string(),
  source: z.string(),
  strength: z.string(),
  open: z.number(),
  confirmed: z.number(),
  corrected: z.number(),
  total: z.number(),
})
const rulesSchema = z.object({
  case: z.array(ruleRecord),
  all_cases: z.array(ruleRecord),
})
export type RuleRecord = z.infer<typeof ruleRecord>

export interface JudgementFilter {
  sourceDocumentId?: string
  status?: string
  strength?: string
  ruleId?: string
  origin?: string
}

export async function listJudgements(caseId: string, filter: JudgementFilter = {}) {
  const query = new URLSearchParams({ case_id: caseId })
  if (filter.sourceDocumentId) query.set("source_document_id", filter.sourceDocumentId)
  if (filter.status) query.set("status", filter.status)
  if (filter.strength) query.set("strength", filter.strength)
  if (filter.ruleId) query.set("rule_id", filter.ruleId)
  if (filter.origin) query.set("origin", filter.origin)
  return listSchema.parse(await fetchAPI(`/api/financial/judgements?${query}`)).items
}

export async function judgementCounts(caseId: string) {
  return countsSchema.parse(
    await fetchAPI(`/api/financial/judgements/counts?case_id=${caseId}`)
  )
}

export async function processorRules(caseId: string) {
  return rulesSchema.parse(
    await fetchAPI(`/api/financial/judgements/rules?case_id=${caseId}`)
  )
}

export async function confirmJudgement(caseId: string, id: string) {
  return judgementSchema.parse(
    await fetchAPI(`/api/financial/judgements/${id}/confirm?case_id=${caseId}`, {
      method: "POST",
      body: {},
    })
  )
}

export async function correctJudgement(caseId: string, id: string, reason: string) {
  return judgementSchema.parse(
    await fetchAPI(`/api/financial/judgements/${id}/correct?case_id=${caseId}`, {
      method: "POST",
      body: { reason },
    })
  )
}

/** The marker's short label: plain words, no rule ids. */
export function strengthLabel(judgement: Pick<Judgement, "strength">) {
  return judgement.strength === "inferred" ? "Inferred" : "Checked guess"
}

export function strengthHelp(judgement: Pick<Judgement, "strength">) {
  return judgement.strength === "inferred"
    ? "The page does not print this value; the processor worked it out."
    : "The processor chose this reading, and the printed balances or totals still prove it."
}

export function statusLabel(judgement: Pick<Judgement, "status">) {
  return judgement.status === "confirmed"
    ? "Looks right"
    : judgement.status === "corrected"
      ? "Corrected"
      : "Not yet checked"
}

/** Which existing correction path fixes this value. */
export function correctionPath(judgement: Pick<Judgement, "subject_type" | "target_key">) {
  if (judgement.subject_type === "transaction") return "payment" as const
  const key = judgement.target_key
  if (key === "opening_balance" || key === "closing_balance") return "balances" as const
  if (key === "currency") return "currency" as const
  if (key === "period_start" || key === "period_end") return "period" as const
  if (key === "account") return "account_number" as const
  if (key === "holder") return "holder" as const
  return "statement" as const
}

export function countLine(counts: Record<string, number | string | null> | undefined) {
  const total = Number(counts?.total || 0)
  if (!total) return ""
  const inferred = Number(counts?.inferred || 0)
  const open = Number(counts?.open || 0)
  return (
    `${total} judgement call${total === 1 ? "" : "s"}` +
    (inferred ? ` · ${inferred} inferred` : "") +
    (open && open !== total ? ` · ${open} not yet checked` : "")
  )
}
