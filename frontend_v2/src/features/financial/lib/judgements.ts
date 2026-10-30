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
  priority: z.number().optional().default(1),
  priority_label: z.string().optional().default(""),
  priority_reason: z.string().nullable().optional(),
  payment_description: z.string().nullable().optional(),
  payment_amount_minor: z.string().nullable().optional(),
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
  priorities: z.array(z.object({ key: z.number(), label: z.string(), help: z.string() })).optional().default([]),
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
  priority: z.number().optional().default(1),
  priority_label: z.string().optional().default(""),
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
  priority?: string[]
  offset?: number
  limit?: number
}

function judgementQuery(caseId: string, filter: JudgementFilter) {
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
    ["priority", filter.priority],
  ]
  for (const [key, values] of lists) for (const value of values || []) query.append(key, value)
  return query
}

/** The CSV of every call matching these filters (not one page of them), with its priority. */
export function judgementExportUrl(caseId: string, filter: JudgementFilter = {}) {
  const query = judgementQuery(caseId, { ...filter, sourceDocumentId: undefined, statementPeriodId: undefined })
  return `/api/financial/judgements/export?${query}`
}

export async function searchJudgements(caseId: string, filter: JudgementFilter = {}) {
  const query = judgementQuery(caseId, filter)
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

/** The marker's short label: plain words, no rule ids. Work Claude did for a person has its own. */
export function strengthLabel(judgement: Pick<Judgement, "strength"> & { origin?: string; rule_id?: string }) {
  if (judgement.origin === "agent")
    return judgement.rule_id === "model.statement_save" ? "Saved by Claude · not confirmed" : "Hand entry by Claude"
  return judgement.strength === "inferred" ? "Inferred" : "Checked guess"
}

export function strengthHelp(judgement: Pick<Judgement, "strength"> & { origin?: string; rule_id?: string }) {
  if (judgement.origin === "agent" && judgement.rule_id === "model.statement_save")
    return "Claude saved this statement's payments for a person. No person has confirmed them against the statement yet."
  if (judgement.origin === "agent")
    return judgement.strength === "inferred"
      ? "Entered by hand by Claude, for a person, from the page images; the printed balances alone do not prove it. Not a person's entry until a person confirms it."
      : "Entered by hand by Claude, for a person, from the page images; checked against the printed balances and totals. Not a person's entry until a person confirms it."
  if (judgement.rule_id === "holder.printed_on_statement")
    return "The page prints this name. Which person holds the account has not been established, so filing the statement under the name printed on it is a judgement call."
  return judgement.strength === "inferred"
    ? "The page does not print this value; the processor worked it out."
    : "The processor chose this reading, and the printed balances or totals still prove it."
}

export const STRENGTH_LABELS: Record<string, string> = {
  inferred: "Inferred",
  proved: "Checked guess",
}
export const ORIGIN_LABELS: Record<string, string> = {
  agent: "Claude, for a person",
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
    (open && open !== total ? ` · ${open} not yet checked` : "") +
    (Number(counts?.priority_1 || 0) ? ` · ${Number(counts?.priority_1)} to check first` : "")
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
export const JUDGEMENT_KEYS = ["jq", "jStatus", "jPriority", "jType", "jStrength", "jBy", "jFiles", "jAccounts", "jPage"]

/**
 * Priority, computed by the backend from what a call can change if it is wrong (never set by hand):
 * 1 the money itself, 2 whose money / which account or statement, 3 description only. Each tier has a text
 * label and an icon as well as its colour, so colour is never the only signal.
 */
export const PRIORITY_LABELS: Record<string, string> = {
  "1": "Check first",
  "2": "Check soon",
  "3": "When convenient",
}
export const PRIORITY_HELP: Record<string, string> = {
  "1": "Can change the money itself: an amount, its direction, a balance, a payment date or a payment entered by hand.",
  "2": "Can change whose money it is, which account or statement it is filed in, or which copy counts.",
  "3": "Can change only how a payment is described.",
}
// Row tint + left border, and the label's own colours. Light and dark text on these pass WCAG AA (checked in STATUS).
export const PRIORITY_ROW: Record<string, string> = {
  "1": "border-l-4 border-l-[#b41624] bg-[#fdf1f2] dark:border-l-[#ff6b7a] dark:bg-[#2a1316]",
  "2": "border-l-4 border-l-[#b45309] bg-[#fdf6e9] dark:border-l-[#f5a524] dark:bg-[#2a2012]",
  "3": "border-l-4 border-l-[#64748b] bg-[#f5f6f8] dark:border-l-[#94a3b8] dark:bg-[#1b1e24]",
}
export const PRIORITY_BADGE: Record<string, string> = {
  "1": "bg-[#fde6e8] text-[#8f1020] dark:bg-[#4a1219] dark:text-[#ffc2c9]",
  "2": "bg-[#fdf0d5] text-[#7a4600] dark:bg-[#47330f] dark:text-[#fbd38d]",
  "3": "bg-[#e9ecf1] text-[#334155] dark:bg-[#2a303a] dark:text-[#d6dde8]",
}

/** The most urgent tier among a row's calls (1 is most urgent); 0 when it has none. */
export function topPriority(items: Pick<Judgement, "priority">[]) {
  return items.length ? Math.min(...items.map((item) => item.priority || 1)) : 0
}
