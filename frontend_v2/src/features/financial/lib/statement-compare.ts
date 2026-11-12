import { z } from "zod"

/** The stored facts of an imported statement (GET .../sources/{id}/compare-facts). */
export const compareFactsResponse = z.object({
  case_id: z.string(),
  source_document_id: z.string(),
  evidence_file_id: z.string(),
  filename: z.string(),
  institution: z.string(),
  account_number: z.string(),
  holder: z.string(),
  period_start: z.string(),
  period_end: z.string(),
  currency: z.string(),
  balance_convention: z.string(),
  pages: z.array(z.number().int().positive()),
  opening_balance_minor: z.string().nullable(),
  closing_balance_minor: z.string().nullable(),
  payment_count: z.number().int().nonnegative(),
  money_in_minor: z.string(),
  money_out_minor: z.string(),
  held_from_ledger: z.number().int().nonnegative(),
  mixed_currency: z.boolean(),
})

/** "Pages 5 to 8", "Page 1". */
export function pageRange(pages: number[], start: number) {
  const sorted = [...pages].sort((a, b) => a - b)
  if (!sorted.length) return `From page ${start}`
  const first = sorted[0],
    last = sorted[sorted.length - 1]
  return first === last ? `Page ${first}` : `Pages ${first} to ${last}`
}
