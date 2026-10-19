import { z } from "zod"

const minor = z.union([z.string().regex(/^-?\d+$/), z.number().int().safe()])
const printedField = z.object({
  text: z.string(),
  start: z.number().int().nonnegative(),
  end: z.number().int().nonnegative(),
})
const endpoint = z.object({
  party: printedField.extend({
    name: z.string(),
    qualifier: z.string().nullable(),
  }),
  bank: printedField,
  account: printedField.extend({ kind: z.literal("clabe") }),
})
const transferDetails = z.object({
  method: z.literal("SPEI"),
  layout: z.literal("kapital-delimited-spei"),
  direction: z.enum(["credit", "debit"]),
  sender: endpoint,
  recipient: endpoint,
  payment_references: z.array(printedField),
  ownership_established: z.literal(false),
})
export type TransferDetails = z.infer<typeof transferDetails>
export const transactionDetail = z.object({
  counterparty_link: z
    .object({
      kind: z.enum(["party", "account"]),
      id: z.string().uuid(),
      label: z.string(),
      recorded_id: z.string().uuid().optional(),
    })
    .nullable()
    .optional(),
  canonical_account_id: z.string().nullable().optional(),
  canonical_account_label: z.string().nullable().optional(),
  account_alias_ids: z.array(z.string()).optional(),
  transfer_details: transferDetails.nullable().optional(),
  category: z.string().optional(),
  from_name: z.string().optional(),
  to_name: z.string().optional(),
  label_version: z.number().int().nonnegative().optional(),
  label_sources: z
    .object({
      category: labelOrigin().optional(),
      from_name: labelOrigin().optional(),
      to_name: labelOrigin().optional(),
    })
    .optional(),
  balance_status: z.enum(["recorded", "not_printed", "unavailable"]).optional(),
  account_type: z.string().optional(),
  account_label: z.string().optional(),
  key: z.string(),
  case_id: z.string(),
  account_id: z.string(),
  source_document_id: z.string(),
  ingestion_run_id: z.string(),
  statement_period_id: z.string().nullable(),
  ref_id: z.string(),
  row_index: z.number(),
  amount_minor: minor,
  currency: z.string(),
  direction: z.string(),
  running_balance_minor: minor.nullable(),
  transaction_date: z.string().nullable(),
  posted_date: z.string().nullable(),
  value_date: z.string().nullable(),
  effective_date: z.string().nullable(),
  ordering_date: z.string(),
  ordering_date_source: z.string(),
  ordering_date_context: z.literal("statement_end_ordering_only").optional(),
  description: z.string().nullable(),
  counterparty_raw: z.string().nullable(),
  transaction_type: z.string().nullable(),
  bank_reference: z.string().nullable(),
  proof_class: z.string(),
  extraction_layer: z.number(),
  ledger_status: z.string(),
  quarantine_reason: z.string().nullable(),
  superseded_by_id: z.string().nullable(),
  locator: z.unknown().optional(),
})

function labelOrigin() {
  return z.object({
    source: z.enum([
      "description",
      "statement",
      "account",
      "investigator",
      "missing",
    ]),
    explanation: z.string().optional(),
    rule: z.string().optional(),
    version: z.string().optional(),
    value: z.string().optional(),
  })
}
