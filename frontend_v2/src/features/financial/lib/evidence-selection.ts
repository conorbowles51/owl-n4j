import { z } from "zod"

export const intakeSelection = z.object({
  case_id: z.string(),
  skipped_non_pdf: z.number().int().nonnegative(),
  files: z.array(
    z.object({
      id: z.string(),
      original_filename: z.string(),
      status: z.string(),
      financial_removed: z.boolean(),
      financial_visibility_revision: z.string(),
    })
  ),
})
export type IntakeSelection = z.infer<typeof intakeSelection>
