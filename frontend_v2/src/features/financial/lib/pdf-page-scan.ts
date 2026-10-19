import { z } from "zod"
const index = z.number().int().nonnegative(),
  cell = z.object({ expected_text: z.string(), column_index: index })
export const resultSchema = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  start_page: index,
  end_page: index,
  table_index: index,
  date_column: index.nullable(),
  amount_column: index.nullable(),
  auto_columns: z.boolean().default(false),
  currency: z.string(),
  applied: z.literal(false),
  limitation: z.string(),
  suggested_rows: index,
  undated_charge_rows: index.default(0),
  pages: z
    .array(
      z.object({
        page_number: index,
        checked: z.boolean(),
        reason: z.string().nullable(),
        checked_rows: index,
        chosen_columns: z
          .object({
            date_column: index,
            amount_column: index,
            additional_amount_columns: z.array(index).max(7).default([]),
            alignment_source: cell.optional(),
            supporting_rows: index.optional(),
            header_support: index.optional(),
          })
          .optional(),
        source_section: z
          .object({
            start_row: index,
            end_row: index,
            start_source: cell,
            end_source: cell,
            omitted_rows: index,
            limitation: z.string(),
          })
          .refine((v) => v.end_row > v.start_row + 1)
          .nullable()
          .optional(),
        other_tables: index.optional(),
        source_revision: z.string().optional(),
        undated_checked_rows: index.optional(),
        undated_charges: z
          .array(
            z.object({
              row_index: index,
              label_source: cell,
              amount_sources: z.array(cell).min(1),
              date_unknown: z.literal(true),
              reason: z.string(),
            })
          )
          .default([]),
        suggestions: z.array(
          z.object({
            row_index: index,
            date_source: cell,
            amount_source: cell,
            amount_header_source: cell.optional(),
          })
        ),
      })
    )
    .max(50),
})
export type PdfPageScan = z.infer<typeof resultSchema>
