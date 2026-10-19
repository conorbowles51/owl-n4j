import { z } from "zod"

const minor = z.string().regex(/^-?\d+$/)
export const statementCalculation = z.object({
  available: z.boolean(),
  currency: z.string().nullish(),
  balance_convention: z.string().optional(),
  opening_minor: minor.nullish(),
  credit_minor: minor.nullish(),
  debit_minor: minor.nullish(),
  calculated_closing_minor: minor.nullish(),
  printed_closing_minor: minor.nullish(),
  difference_minor: minor.nullish(),
})
export const statementBlocker = z.object({
  message: z.string(),
  row_id: z.string().nullish(),
  field: z.string().optional(),
  kind: z.string().optional(),
  code: z.string().optional(),
  reason_id: z.string().optional(),
  expected_format: z.string().optional(),
  expected_minor: minor.nullish(),
  printed_minor: minor.nullish(),
  difference_minor: minor.nullish(),
  target: z
    .object({
      kind: z.string(),
      field: z.string().nullish(),
      row_id: z.string().nullish(),
      page: z.number().nullish(),
    })
    .optional(),
})
export const statementAssessment = z.object({
  can_import: z.boolean(),
  status: z.string(),
  revision: z.string().optional(),
  assessment_current: z.boolean().optional(),
  blockers: z.array(statementBlocker),
  calculation: statementCalculation.nullish(),
})
