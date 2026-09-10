import { z } from "zod"

export const summaryContribution = z.object({
  transaction_id: z.string().uuid(),
  ref_id: z.string(),
  currency: z.string(),
  amount_minor: z.string().regex(/^(0|[1-9][0-9]*)$/),
  direction: z.enum(["credit", "debit"]),
  ordering_date: z.string().nullable(),
  proof_class: z.enum(["p0", "p1", "p2", "p3"]),
  source_proof_class: z.enum(["p0", "p1", "p2", "p3"]),
  source_document_id: z.string().uuid(),
})
export type SummaryContribution = z.infer<typeof summaryContribution>

export function validateSummaryContributions(
  rows: SummaryContribution[] | undefined,
  groups: {
    currency: string
    rows: number
    credits_minor: string
    debits_minor: string
  }[],
  working: boolean
) {
  if (!rows) return // Older responses remain readable without drill-down.
  if (
    new Set(rows.map((r) => r.transaction_id)).size !== rows.length ||
    rows.some(
      (r) =>
        !groups.some((g) => g.currency === r.currency) ||
        (!working && (r.proof_class === "p3" || r.source_proof_class === "p3"))
    )
  )
    throw Error("Summary source membership disagrees with its totals.")
  for (const group of groups) {
    const selected = rows.filter((r) => r.currency === group.currency)
    const sum = (direction: string) =>
      selected
        .filter((r) => r.direction === direction)
        .reduce((n, r) => n + BigInt(r.amount_minor), 0n)
    if (
      selected.length !== group.rows ||
      sum("credit") !== BigInt(group.credits_minor) ||
      sum("debit") !== BigInt(group.debits_minor)
    )
      throw Error("Summary source amounts disagree with their totals.")
  }
}
