import { z } from "zod"

export const paymentDocumentSchema =
  "loupe.financial.payment_document/1" as const
export const paymentDocumentProposal = z.object({
  schema: z.literal(paymentDocumentSchema),
  version: z.string(),
  kind: z.enum(["wire_report", "deposit_receipt"]),
  document_id: z
    .string()
    .regex(/^[a-f0-9]{64}$/)
    .optional(),
  case_id: z.string(),
  evidence_file_id: z.string(),
  filename: z.string(),
  revision: z.string().regex(/^[a-f0-9]{64}$/),
  file_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  supported: z.boolean(),
  page_numbers: z.array(z.number().int().positive()).min(1),
  creates_transactions: z.literal(false),
  issues: z.array(z.string()),
  fields: z.array(
    z.object({
      key: z.string(),
      label: z.string(),
      printed_label: z.string(),
      input_type: z.enum(["text", "amount", "currency", "date"]),
      raw: z.string(),
      value: z.string(),
      issues: z.array(z.string()),
      source_cells: z.array(
        z.object({ expected_text: z.string(), locator: z.unknown() })
      ),
    })
  ),
})
export type PaymentDocumentProposal = z.infer<typeof paymentDocumentProposal>
export const savedPaymentDocument = z.object({
  schema: z.literal(paymentDocumentSchema),
  original: paymentDocumentProposal,
  reviewed_values: z.record(z.string(), z.string()),
  correction_reasons: z.record(z.string(), z.string()),
  notes: z.string(),
  link_reason: z.string(),
})
