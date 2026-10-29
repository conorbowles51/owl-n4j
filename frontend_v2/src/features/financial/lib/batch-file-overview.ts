import { z } from "zod"

/** Which files in a batch are copies of statements kept elsewhere, as the batch reports them. */
export const batchFileOverview = z.array(
  z.object({
    file_id: z.string(),
    filename: z.string(),
    statements: z.number().int().nonnegative(),
    copies: z.number().int().nonnegative(),
    unfinished: z.number().int().nonnegative(),
    saved: z.number().int().nonnegative(),
    all_copies: z.boolean(),
    retained: z.array(
      z.object({
        filename: z.string(),
        evidence_file_id: z.string().nullish(),
        copies: z.number().int().nonnegative(),
      })
    ),
  })
)
export type BatchFileOverviewEntry = z.infer<typeof batchFileOverview>[number]
