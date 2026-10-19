import { z } from "zod"
const day = z.string().regex(/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/)
const count = z.number().int().nonnegative()
export const statementCoverage = z.object({
  case_id: z.string(),
  account_id: z.string().nullable().optional(),
  offset: count,
  has_more: z.boolean(),
  applied: z.literal(false),
  limitation: z.string(),
  items: z.array(
    z.object({
      account_id: z.string(),
      label: z.string(),
      holder: z.string().nullable().optional(),
      identifier: z.string().nullable().optional(),
      institution: z.string().nullable().optional(),
      currency: z.string().nullable().optional(),
      available: z.boolean(),
      reason: z.string().nullable(),
      periods: z.array(
        z.object({
          period_id: z.string(),
          source_document_id: z.string(),
          evidence_file_id: z.string().nullable(),
          filename: z.string().nullable().optional(),
          currency: z.string(),
          start: day.nullable(),
          end: day.nullable(),
          included: z.boolean(),
          exclusion_reason: z
            .enum([
              "source_not_admitted",
              "missing_dates",
              "dates_not_printed",
              "invalid_date_range",
            ])
            .nullable(),
        })
      ),
      currencies: z.array(
        z.object({
          currency: z.string(),
          period_count: count,
          covered_days: count,
          uncovered_days: count,
          windows: z.array(
            z.object({ start: day, end: day, period_ids: z.array(z.string()) })
          ),
          gaps: z.array(z.object({ start: day, end: day, days: count })),
          overlaps: z.array(
            z.object({ period_id: z.string(), start: day, end: day })
          ),
        })
      ),
    })
  ),
})

export type StatementCoverageAccount = z.infer<
  typeof statementCoverage
>["items"][number]
