import { z } from "zod"

export const savedStatementPosition = z.object({
  case_id: z.string(),
  source_document_id: z.string(),
  evidence_file_id: z.string(),
  pages: z.array(z.number().int().positive()),
  source_position_rows: z
    .array(
      z.object({
        id: z.string(),
        page_number: z.number().int().positive(),
        kind: z.enum(["transaction", "unresolved"]),
        fields: z.record(z.string(), z.string()),
      })
    )
    .default([]),
  requires_manual_position: z.boolean().default(false),
})
