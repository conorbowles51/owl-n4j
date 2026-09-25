import { z } from "zod"

const revision = z.string().regex(/^[a-f0-9]{64}$/)

export const retainedStatement = z.object({
  evidence_file_id: z.string().uuid(),
  statement_id: revision.nullish(),
  source_document_id: z.string().uuid().nullish(),
  filename: z.string(),
  page_number: z.number().int().positive().default(1),
})

export const statementDuplicateDisposition = z
  .object({
    policy: z.string(),
    reading_revision: revision,
    revision,
    status: z.enum([
      "ignored",
      "retained",
      "not_duplicate",
      "needs_comparison",
      "restored",
    ]),
    label: z.string(),
    reason: z.string(),
    current: z.boolean(),
    matched_fields: z.array(z.string()).default([]),
    basis: z.enum(["identical_bytes", "identical_financial_reading"]).nullish(),
    retained: retainedStatement.nullish(),
  })
  .passthrough()

export const statementDuplicateResponse = z.object({
  case_id: z.string().uuid(),
  evidence_file_id: z.string().uuid(),
  statement_id: revision.nullish(),
  duplicate_disposition: statementDuplicateDisposition,
})

export type RetainedStatement = z.infer<typeof retainedStatement>
export type StatementDuplicateDisposition = z.infer<
  typeof statementDuplicateDisposition
>
