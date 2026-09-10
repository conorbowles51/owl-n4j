import { z } from "zod"
export const ledgerTimeline = z.object({
  case_id: z.string(),
  account_id: z.string().nullable(),
  start_date: z.string().nullable(),
  end_date: z.string().nullable(),
  population: z.enum(["working", "verified"]),
  snapshot_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  excluded_rows: z.number().int().nonnegative(),
  limitation: z.string(),
  rows: z
    .array(
      z.object({
        key: z.string(),
        source_document_id: z.string(),
        account_id: z.string(),
        account_label: z.string(),
        chronology_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
        chronology_basis: z.enum([
          "value_date",
          "transaction_date",
          "posted_date",
          "effective_date",
          "ordering_date",
          "statement_end_ordering_only",
        ]),
        ordering_date: z.string(),
        direction: z.enum(["debit", "credit"]),
        amount_minor: z.string().regex(/^(0|[1-9][0-9]*)$/),
        currency: z.string(),
        proof_class: z.enum(["p0", "p1", "p2", "p3"]),
        description: z.string().nullable(),
      })
    )
    .max(1000),
})
export type LedgerTimeline = z.infer<typeof ledgerTimeline>
export const chronologyLabels = {
  value_date: "Value date",
  transaction_date: "Transaction date",
  posted_date: "Posted date",
  effective_date: "Effective date",
  ordering_date: "Ordering date only",
  statement_end_ordering_only:
    "Transaction date unknown — statement-end ordering only",
}

export function validContextDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}(?:$|T| )/.test(value))
    return false
  const day = value.slice(0, 10)
  const stamp = new Date(day + "T00:00:00Z")
  return (
    !Number.isNaN(stamp.getTime()) && stamp.toISOString().slice(0, 10) === day
  )
}
