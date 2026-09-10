import { z } from "zod"
const citation = z.object({
  row_index: z.number().int().nonnegative(),
  column_index: z.number().int().nonnegative(),
  expected_text: z.string(),
  locator: z.unknown(),
})
export const layoutContext = z.object({
  layout_id: z.literal("capital-one-platinum-card-sections"),
  version: z.literal(1),
  institution_source: citation,
  printed_card_source: citation,
  cycle_source: citation,
  cycle_count_source: citation.nullable().optional(),
  start_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  end_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  rows: z
    .array(
      z.object({
        row_index: z.number().int().nonnegative(),
        card_ending: z.string().regex(/^\d{4}$/),
        printed_section: z.enum([
          "Payments, Credits and Adjustments",
          "Transactions",
        ]),
        section_source: citation,
        date_source: citation,
        date_label: z.enum(["Date", "Trans Date"]).default("Date"),
        date_header_source: citation.optional(),
        posting_date_source: citation.nullable().optional(),
        posting_date_header_source: citation.nullable().optional(),
        posting_date_proposals: z
          .array(z.string().regex(/^\d{4}-\d{2}-\d{2}$/))
          .max(2)
          .default([]),
        description_source: citation,
        amount_source: citation,
        date_proposals: z.array(z.string().regex(/^\d{4}-\d{2}-\d{2}$/)).max(2),
        direction: z.null(),
        requires_source_review: z.literal(true),
      })
    )
    .max(1000),
  applied: z.literal(false),
  limitation: z.string(),
})
export type StatementLayoutContext = z.infer<typeof layoutContext>
export type LayoutCitation = z.infer<typeof citation>
