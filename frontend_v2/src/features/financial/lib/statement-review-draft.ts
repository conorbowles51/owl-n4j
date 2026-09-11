import { z } from "zod"

const draftRow = z.object({
  id: z.string(),
  excluded: z.boolean(),
  manual_page: z.number().int().positive().nullable().optional(),
  date: z.string(),
  description: z.string(),
  counterparty: z.string(),
  amount_minor: z.string(),
  direction: z.enum(["credit", "debit"]),
  balance_minor: z.string().nullable(),
  reason: z.string(),
})
export const statementDraft = z.object({
  revision: z.string(),
  rows: z.array(draftRow).max(1000),
  holder: z.string(),
  account: z.string(),
  institution: z.string(),
  periodStart: z.string(),
  periodEnd: z.string(),
  detailsReason: z.string(),
  amountText: z.record(z.string(), z.string()),
})
export type StatementDraft = z.infer<typeof statementDraft>

export function readStatementDraft(
  key: string | null,
  revision: string
): StatementDraft | null {
  if (!key) return null
  try {
    const raw = sessionStorage.getItem(key)
    if (!raw) return null
    const draft = statementDraft.parse(JSON.parse(raw))
    return draft.revision === revision ? draft : null
  } catch {
    return null
  }
}

export function saveStatementDraft(
  key: string | null,
  draft: StatementDraft
): boolean {
  if (!key) return false
  try {
    sessionStorage.setItem(key, JSON.stringify(statementDraft.parse(draft)))
    return true
  } catch {
    return false
  }
}
