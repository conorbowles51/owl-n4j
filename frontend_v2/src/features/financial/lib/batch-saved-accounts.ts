import { z } from "zod"

export const batchSavedAccountsScope = z.object({
  case_id: z.string(),
  batch_id: z.string(),
  revision: z.string(),
  source_document_ids: z.array(z.string()),
  account_ids: z.array(z.string().min(1)),
  statement_count: z.number(),
  transaction_count: z.number(),
  start_date: z.string().nullable(),
  end_date: z.string().nullable(),
})
