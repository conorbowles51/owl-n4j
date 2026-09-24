import { z } from "zod"

const draftRow = z.object({
  id: z.string(),
  excluded: z.boolean(),
  manual_page: z.number().int().positive().nullable().optional(),
  date: z.string(),
  date_unprinted: z.boolean().optional(),
  date_values: z
    .partialRecord(z.enum(["date", "booking_date", "value_date"]), z.string())
    .optional(),
  description: z.string(),
  counterparty: z.string(),
  counterparty_link: z
    .object({ kind: z.enum(["party", "account"]), id: z.string().uuid() })
    .nullable()
    .optional(),
  amount_minor: z.string(),
  direction: z.enum(["credit", "debit", ""]),
  balance_minor: z.string().nullable(),
  reason: z.string(),
})
export const statementDraft = z.object({
  revision: z.string(),
  // New drafts retain only changes; older complete drafts remain readable.
  row_mode: z.literal("changes").optional(),
  rows: z.array(draftRow).max(100000),
  holder: z.string(),
  account: z.string(),
  institution: z.string(),
  periodStart: z.string(),
  periodEnd: z.string(),
  detailsReason: z.string(),
  noActivityRevision: z.string().optional(),
  balanceException: z
    .object({ revision: z.string(), reason: z.string() })
    .optional(),
  coverageDecision: z
    .object({ revision: z.string(), reason: z.string() })
    .optional(),
  amountText: z.record(z.string(), z.string()),
})
export type StatementDraft = z.infer<typeof statementDraft>

export function serverStatementDraft(raw: Record<string, unknown> | undefined) {
  if (!raw) return null
  const parsed = statementDraft.safeParse({
    revision: raw.expected_revision,
    rows: Array.isArray(raw.rows)
      ? raw.rows.map((row) => ({
          ...row,
          direction: row.direction || "",
          date: row.date ?? "",
          counterparty: row.counterparty ?? "",
          description: row.description ?? "",
          amount_minor: row.amount_minor ?? "",
          balance_minor: row.balance_minor ?? null,
          reason: row.reason ?? "",
        }))
      : [],
    holder: raw.holder ?? "",
    account: raw.account_number ?? "",
    institution: raw.institution ?? "",
    periodStart: raw.period_start ?? "",
    periodEnd: raw.period_end ?? "",
    detailsReason: raw.details_reason || "",
    noActivityRevision: raw.no_activity_confirmed
      ? raw.no_activity_revision || ""
      : "",
    balanceException: {
      revision: raw.balance_exception_revision || "",
      reason: raw.balance_exception_reason || "",
    },
    coverageDecision: {
      revision: raw.coverage_review_revision || "",
      reason: raw.coverage_review_reason || "",
    },
    amountText: {},
  })
  return parsed.success ? parsed.data : null
}

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
