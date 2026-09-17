import { z } from "zod"

export const reviewRecoverySchema = z.object({
  revision: z.string(),
  required: z.boolean(),
  acknowledged: z.boolean(),
  unmatched_count: z.number(),
  reviews: z.array(
    z.object({
      id: z.string(),
      filename: z.string(),
      evidence_file_id: z.string(),
      origin: z.string(),
      holder: z.string(),
      account: z.string(),
      currency: z.string(),
      period_start: z.string(),
      period_end: z.string(),
      row_count: z.number(),
      changed_row_count: z.number(),
      period_found: z.boolean(),
      saved_at: z.string().nullish(),
    })
  ),
})
