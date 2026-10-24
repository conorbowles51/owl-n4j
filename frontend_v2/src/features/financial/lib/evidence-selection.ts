import { z } from "zod"

export const intakeSelection = z.object({
  case_id: z.string(),
  skipped_non_pdf: z.number().int().nonnegative(),
  /** Files inside a selected folder that were removed from Financial; left out unless chosen by name. */
  skipped_removed: z.number().int().nonnegative().default(0),
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
