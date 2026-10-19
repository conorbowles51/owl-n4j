import { z } from "zod"
import { transactionDetail } from "./transaction-detail"

export const citationSchema = z.object({
  transaction: transactionDetail.optional(),
  case_id: z.string(),
  transaction_id: z.string(),
  ref_id: z.string(),
  source_document_id: z.string(),
  evidence_file_id: z.string().uuid(),
  filename: z.string(),
  sha256_at_ingestion: z.string().regex(/^[a-f0-9]{64}$/),
  recorded_digest_matches: z.literal(true),
  file_bytes_verified: z.literal(false),
  locator_state: z.enum(["stored", "missing", "invalid"]),
  locator: z.unknown(),
  ledger_status: z.string(),
  superseded_by_id: z.string().nullable(),
  limitation: z.string(),
})
