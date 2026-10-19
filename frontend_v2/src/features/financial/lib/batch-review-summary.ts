import { z } from "zod"

export const batchReviewSummarySchema = z.object({
  blocked_statements: z.number(),
  importable_with_checks: z.number(),
  imported_with_checks: z.number(),
  unchecked_balance_statements: z.number(),
  groups: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      explanation: z.string(),
      statement_count: z.number(),
      check_count: z.number(),
      blocked_statements: z.number(),
      importable_statements: z.number(),
      imported_statements: z.number(),
    })
  ),
})
