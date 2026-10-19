import { z } from "zod"
import { formatLedgerAmount } from "./ledger-format"
const money = z.string().regex(/^[0-9]+$/)
const transfer = z.object({
  kind: z.literal("transfer-comparison"),
  details: z.object({
    basis: z.string(),
    start_date: z.string().nullable(),
    end_date: z.string().nullable(),
    figures: z.array(
      z.object({
        currency: z.string(),
        posting_rows: z.number().int().nonnegative(),
        movement_count: z.number().int().nonnegative(),
        paired_transfers: z.number().int().nonnegative(),
        paired_amount_minor: money,
        unpaired_credits_minor: money,
        unpaired_debits_minor: money,
      })
    ),
  }),
})
export function savedAnalysisSummary(value: unknown): string[] {
  const parsed = transfer.safeParse(value)
  if (!parsed.success) return []
  const d = parsed.data.details
  const amount = (v: string, c: string) =>
    `${formatLedgerAmount(v, c).text} ${c}`
  return [
    `Comparison dates: ${d.start_date || "all earlier dates"} to ${d.end_date || "all later dates"}.`,
    `Reason for pairing: ${d.basis}`,
    ...d.figures.map(
      (f) =>
        `${f.currency}: ${f.posting_rows} payments counted as ${f.movement_count} movements, including ${f.paired_transfers} selected transfers totalling ${amount(f.paired_amount_minor, f.currency)}. Unpaired credits: ${amount(f.unpaired_credits_minor, f.currency)}. Unpaired debits: ${amount(f.unpaired_debits_minor, f.currency)}.`
    ),
    "These totals describe the comparison when saved. The linked payment buttons below identify the source records attached to this note; unpaired payments may be outside that selection. Recalculate in Transfers to use current records.",
  ]
}
