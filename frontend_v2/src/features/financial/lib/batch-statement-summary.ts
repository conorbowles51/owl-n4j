import { z } from "zod"

// Whole-batch, mutually exclusive review states. This is separate from the
// filtered item count and from overlapping review-reason groups.
export const batchStatementSummary = z.object({
  total: z.number().int().nonnegative(),
  available: z.number().int().nonnegative(),
  blocked: z.number().int().nonnegative(),
  imported: z.number().int().nonnegative(),
  pending_import: z.number().int().nonnegative(),
  skipped: z.number().int().nonnegative(),
  possible_duplicates: z.number().int().nonnegative().default(0),
  duplicate_ignored: z.number().int().nonnegative(),
  assigned: z.number().int().nonnegative(),
  other: z.number().int().nonnegative(),
  available_with_payments: z.number().int().nonnegative(),
  available_no_activity: z.number().int().nonnegative(),
  available_other: z.number().int().nonnegative(),
})
export type BatchStatementSummary = z.infer<typeof batchStatementSummary>
