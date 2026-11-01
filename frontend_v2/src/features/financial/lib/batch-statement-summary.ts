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
  /** The review queue's lists for this batch's unsaved statements; null until the queue has been built. */
  queue: z
    .object({
      still_to_finish: z.number().int().nonnegative(),
      ready: z.number().int().nonnegative().default(0),
      filled: z.number().int().nonnegative().default(0),
      saving: z.number().int().nonnegative().default(0),
      rechecking: z.number().int().nonnegative().default(0),
      reader_fix: z.number().int().nonnegative().default(0),
      unreadable: z.number().int().nonnegative().default(0),
      copies: z.number().int().nonnegative().default(0),
      not_payment: z.number().int().nonnegative().default(0),
      left_unimported: z.number().int().nonnegative().default(0),
      imported: z.number().int().nonnegative().default(0),
      assigned: z.number().int().nonnegative().default(0),
    })
    .nullish(),
})
export type BatchStatementSummary = z.infer<typeof batchStatementSummary>
