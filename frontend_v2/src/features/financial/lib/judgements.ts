import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import type { LedgerTransaction } from "../api"

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
  category: z.string().optional().default(""),
  category_label: z.string().optional().default(""),
  working_notes: z.string().nullable().optional(),
  period_start: z.string().nullable().optional(),
  period_end: z.string().nullable().optional(),
  account_label: z.string().nullable().optional(),
  status: z.enum(["open", "confirmed", "corrected"]),
  resolved_by: z.string().nullable(),
  resolved_at: z.string().nullable(),
  resolution_reason: z.string().nullable(),
  adjudication_id: z.string().nullable(),
})
export type Judgement = z.infer<typeof judgementSchema>

const option = z.object({ value: z.string(), label: z.string() })
const listSchema = z.object({
  items: z.array(judgementSchema),
  total: z.number().optional().default(0),
  offset: z.number().optional().default(0),
  facets: z.record(z.string(), z.record(z.string(), z.number())).optional().default({}),
  categories: z.array(z.object({ key: z.string(), label: z.string() })).optional().default([]),
  rules: z.array(z.tuple([z.string(), z.string(), z.string()])).optional().default([]),
  accounts: z.array(option).optional().default([]),
  files: z.array(option).optional().default([]),
})
export type JudgementPage = z.infer<typeof listSchema>
const rowMapSchema = z.object({
  judgements: z.array(judgementSchema),
  transactions: z.record(z.string(), z.array(z.string())),
  documents: z.record(z.string(), z.array(z.string())),
  categories: z.array(z.object({ key: z.string(), label: z.string() })),
})
export type JudgementRowMap = z.infer<typeof rowMapSchema>
const previewItem = z.object({
  rule_id: z.string(),
  rule_label: z.string(),
  rule_source: z.string(),
  subject_type: z.string(),
  row_id: z.string().nullable(),
  strength: z.enum(["proved", "inferred"]),
  summary: z.string(),
  target_key: z.string(),
  category: z.string(),
  category_label: z.string(),
  page: z.union([z.number(), z.string()]).nullable().optional(),
})
export type JudgementPreview = z.infer<typeof previewItem>
const tally = z.record(z.string(), z.union([z.number(), z.string(), z.null()]))
const countsSchema = z.object({
  case: tally,
  statements: z.record(z.string(), tally),
  periods: z.record(z.string(), tally).optional().default({}),
  accounts: z.record(z.string(), tally).optional().default({}),
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
  statementPeriodId?: string
  q?: string
  status?: string[]
  strength?: string[]
  origin?: string[]
  category?: string[]
  ruleId?: string[]
  fileIds?: string[]
  accountIds?: string[]
  offset?: number
  limit?: number
}

export async function searchJudgements(caseId: string, filter: JudgementFilter = {}) {
  const query = new URLSearchParams({ case_id: caseId })
  if (filter.sourceDocumentId) query.set("source_document_id", filter.sourceDocumentId)
  if (filter.statementPeriodId) query.set("statement_period_id", filter.statementPeriodId)
  if (filter.q?.trim()) query.set("q", filter.q.trim())
  const lists: [string, string[] | undefined][] = [
    ["status", filter.status],
    ["strength", filter.strength],
    ["origin", filter.origin],
    ["category", filter.category],
    ["rule_id", filter.ruleId],
    ["file_id", filter.fileIds],
    ["account_id", filter.accountIds],
  ]
  for (const [key, values] of lists) for (const value of values || []) query.append(key, value)
  if (filter.offset) query.set("offset", String(filter.offset))
  query.set("limit", String(filter.limit ?? 500))
  return listSchema.parse(await fetchAPI(`/api/financial/judgements?${query}`))
}

export async function listJudgements(caseId: string, filter: JudgementFilter = {}) {
  return (await searchJudgements(caseId, filter)).items
}

/** Which ledger payments each call touches, for the whole case in one read. */
export async function judgementRowMap(caseId: string) {
  return rowMapSchema.parse(await fetchAPI(`/api/financial/judgements/rows?case_id=${caseId}`))
}

/** The calls the rules make on a reading before it is saved. Stores nothing. */
export async function previewJudgements(
  caseId: string,
  body: { statement_id: string; currency: string; reading_rows: unknown[]; review_rows: unknown[] }
) {
  return z
    .object({ items: z.array(previewItem) })
    .parse(
      await fetchAPI(`/api/financial/judgements/preview?case_id=${caseId}`, { method: "POST", body })
    ).items
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

/** The marker's short label: plain words, no rule ids. Hand entries by the processing agent have their own. */
export function strengthLabel(judgement: Pick<Judgement, "strength"> & { origin?: string }) {
  if (judgement.origin === "agent") return "Hand entry"
  return judgement.strength === "inferred" ? "Inferred" : "Checked guess"
}

export function strengthHelp(judgement: Pick<Judgement, "strength"> & { origin?: string }) {
  if (judgement.origin === "agent")
    return judgement.strength === "inferred"
      ? "Entered by hand by the processing agent from the page images; the printed balances alone do not prove it."
      : "Entered by hand by the processing agent from the page images; checked against the printed balances and totals."
  return judgement.strength === "inferred"
    ? "The page does not print this value; the processor worked it out."
    : "The processor chose this reading, and the printed balances or totals still prove it."
}

export const STRENGTH_LABELS: Record<string, string> = {
  inferred: "Inferred",
  proved: "Checked guess",
}
export const ORIGIN_LABELS: Record<string, string> = {
  agent: "Processing agent (by hand)",
  processor: "Processor",
}
export const STATUS_LABELS: Record<string, string> = {
  open: "Not yet checked",
  confirmed: "Looks right",
  corrected: "Corrected",
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

/** Index of the case's row map: a payment's own calls, then the calls about its whole statement. */
export function judgementLookup(map: JudgementRowMap | undefined) {
  const byId = new Map((map?.judgements || []).map((judgement) => [judgement.id, judgement]))
  const pick = (ids: string[] | undefined) =>
    (ids || []).map((id) => byId.get(id)).filter((j): j is Judgement => !!j)
  return (transaction: Pick<LedgerTransaction, "key" | "source_document_id">) => [
    ...pick(map?.transactions[transaction.key]),
    ...(transaction.source_document_id ? pick(map?.documents[transaction.source_document_id]) : []),
  ]
}

// The Judgement calls page keeps all its state in the URL, as the review queue does.
export const JUDGEMENT_KEYS = ["jq", "jStatus", "jType", "jStrength", "jBy", "jFiles", "jAccounts", "jPage"]
