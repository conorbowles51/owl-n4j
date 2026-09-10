import { z } from "zod"
const index = z.number().int().nonnegative()
export const sourceTable = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  page_number: z.number().int().positive(),
  table_index: index,
  table_count: z.number().int().positive(),
  source_revision: z.string().regex(/^[a-f0-9]{64}$/),
  table_source: z.enum(["drawn_geometry", "text_alignment"]),
  geometry_source: z.string(),
  text_origin: z
    .enum(["digital_text_layer", "recognised_glyphs", "unknown"])
    .default("unknown"),
  locator: z.unknown(),
  columns: z.array(index).max(64),
  rows: z
    .array(
      z.object({
        row_index: index,
        cells: z.array(
          z.object({
            column_index: index,
            expected_text: z.string().min(1).max(4096),
            locator: z.unknown(),
          })
        ),
      })
    )
    .max(1000),
  applied: z.literal(false),
})
