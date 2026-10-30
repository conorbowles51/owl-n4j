import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { readerReplacementSchema } from "../components/readerReplacement"
import { reviewRecoverySchema } from "./review-recovery"
import { paymentDocumentProposal } from "./payment-document"
import {
  retainedStatement,
  statementDuplicateDisposition,
} from "./statement-duplicate"
import { statementAssessment } from "./statement-assessment"
import { statementModelWork } from "./statement-model-work"

/** One statement as the server reads it for review (GET /api/financial/statement-import/{file}). */
export const cell = z.object({
  column_index: z.number(),
  expected_text: z.string(),
  locator: z.unknown(),
})
export const row = z
  .object({
    id: z.string(),
    page_number: z.number(),
    table_index: z.number(),
    row_index: z.number(),
    source_cells: z.array(cell),
    value_sources: z
      .record(
        z.string(),
        z.object({
          page_number: z.number(),
          table_index: z.number(),
          row_index: z.number(),
          source_cell: cell,
        })
      )
      .optional(),
    // A reading rule can record what a worked-out value rests on (balance_derivation, covered_by) as an object
    // beside the printed strings; those are kept apart in field_details so they stay visible in review.
    fields: z.record(z.string(), z.unknown()),
    // How a reading rule repaired a damaged cell: shown as a judgement call before the statement is saved.
    value_repairs: z.array(z.record(z.string(), z.unknown())).optional(),
    issues: z.array(z.string()),
    excluded: z.boolean(),
    kind: z.string(),
  })
  .transform(({ fields, ...rest }) => {
    const strings: Record<string, string> = {}
    const details: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(fields)) {
      if (typeof value === "string") strings[key] = value
      else if (value !== null && value !== undefined) details[key] = value
    }
    return { ...rest, fields: strings, field_details: details }
  })
// The figures a worked-out balance rests on, as the reading rule recorded them.

export const proposalSchema = z.object({
  recovered_saved_section: z.boolean().default(false),
  statement_page_numbers: z.array(z.number()).default([]),
  document_review: paymentDocumentProposal.optional(),
  reading_failure: z.string().nullish(),
  duplicate_disposition: statementDuplicateDisposition.nullish(),
  case_id: z.string(),
  evidence_file_id: z.string(),
  filename: z.string(),
  currency: z.string(),
  detected_currency: z.string().optional(),
  revision: z.string(),
  review_recovery: reviewRecoverySchema.nullish(),
  row_assignments: z
    .array(
      z.object({
        row_id: z.string(),
        original_statement_id: z.string(),
        target_statement_id: z.string(),
      })
    )
    .default([]),
  saved_review: z
    .object({
      review_revision: z.string(),
      request: z.record(z.string(), z.unknown()),
      saved_at: z.string(),
      saved_by: z.object({ name: z.string() }),
    })
    .nullish(),
  previous_saved_review: z
    .object({
      request: z.record(z.string(), z.unknown()),
      evidence_file_id: z.string(),
      filename: z.string(),
    })
    .nullish(),
  metadata: z.object({
    account_closure: z
      .object({
        date: z.string(),
        page_number: z.number().int().positive(),
        table_index: z.number().int().nonnegative(),
        row_index: z.number().int(),
        source_cells: z.array(
          z.object({ expected_text: z.string(), locator: z.unknown() })
        ),
      })
      .optional(),
    account_type: z.string().optional(),
    balance_convention: z.enum(["asset_balance", "liability_owed"]).optional(),
    institution: z.string(),
    holder: z.string(),
    account_number: z.string(),
    period: z.string(),
    period_start: z.string(),
    period_end: z.string(),
  }),
  rows: z.array(row),
  issues: z.array(z.string()),
  transaction_count: z.number(),
  record_count: z.number().optional(),
  incomplete_count: z.number().optional(),
  can_import_balances: z.boolean().default(false),
  balance_basis: z.enum(["operation", "liquidation"]).nullish(),
  prior_period_settlement_pages: z
    .array(z.number().int().positive())
    .default([]),
  can_record_account_closure: z.boolean().default(false),
  // A statement printing only its closing date: that date, and a start the
  // previous statement for the same card establishes. Used only where the
  // printed header has no date.
  period_dates: z
    .object({
      period_start: z.string().default(""),
      period_end: z.string().default(""),
    })
    .nullish(),
  assignment_only: z.boolean().default(false),
  printed_main_account: z.string().default(""),
  needs_attention: z.number(),
  page_numbers: z.array(z.number()).default([]),
  unassigned_page_numbers: z.array(z.number()).default([]),
  information_pages: z
    .array(z.object({ page_number: z.number(), kind: z.string() }))
    .default([]),
  statement_id: z.string().nullable().optional(),
  statement_choices: z
    .array(
      z.object({
        id: z.string(),
        institution: z.string(),
        layout_id: z.string().optional(),
        account_reference: z.string(),
        account_label: z.string().optional(),
        account_type: z.string().optional(),
        currency: z.string().optional(),
        assignment_only: z.boolean().optional(),
        document_kind: z.literal("deposit_receipt").optional(),
        statement_date: z.string().optional(),
        printed_statement_date: z.string().optional(),
        period_start: z.string(),
        period_end: z.string(),
        page_numbers: z.array(z.number()),
        checks: z
          .object({
            balance_status: z.enum(["matches", "difference", "unavailable"]),
            flagged_rows: z.number(),
            has_difference: z.boolean().optional(),
            transaction_count: z.number().optional(),
          })
          .optional(),
      })
    )
    .default([]),
  current_import: z
    .object({
      source_document_id: z.string(),
      evidence_file_id: z.string(),
      account_id: z.string().nullable().optional(),
      filename: z.string().nullable().optional(),
      revision: z.string(),
      transaction_count: z.number(),
      record_count: z.number().optional(),
      incomplete_count: z.number().optional(),
      currency: z.string().nullable().optional(),
      refresh_available: z.boolean().optional(),
      refresh_review_required: z.boolean().optional(),
      refresh_transaction_count: z.number().optional(),
      refresh_admission: statementAssessment.nullish(),
      refresh_requires_reconciliation: z.boolean().optional(),
      refresh_currency_conflict: z
        .object({
          saved_currency: z.string(),
          reading_currency: z.string(),
          message: z.string(),
        })
        .nullish(),
      details: z
        .object({
          holder: z.string(),
          account_number: z.string(),
          institution: z.string(),
          period_start: z.string(),
          period_end: z.string(),
        })
        .optional(),
      excluded_as_duplicate: z.boolean().default(false),
      model_work: statementModelWork.nullish(),
      retained_filename: z.string().nullable().optional(),
      duplicate_disposition: statementDuplicateDisposition.nullish(),
      duplicate_copies: z.array(retainedStatement).default([]),
      reader_replacement: readerReplacementSchema.nullish(),
      details_reason: z.string().default(""),
      review_decisions: z
        .array(
          z.object({
            description: z.string(),
            date: z.string(),
            excluded: z.boolean(),
            reason: z.string(),
          })
        )
        .default([]),
    })
    .nullable()
    .optional(),
})

export type Proposal = z.infer<typeof proposalSchema>

/**
 * One statement's reading as its review opens it. Shared so the review queue
 * can start it together with the batch item instead of after it (the item
 * request and this one each read the statement on the server; run one after
 * the other they doubled the wait to open a statement). Fresh for a few
 * seconds only: long enough that a reading started just before the review
 * mounts is used rather than read again, short enough that reopening a
 * statement later still reads it afresh.
 */
export const STATEMENT_READING_FRESH_MS = 10_000
// What a reading the review cannot show breaks, in plain words: which line and which value, never a schema dump.
export function readingShapeMessage(issues: { path: PropertyKey[] }[]) {
  const where = (path: PropertyKey[]) => {
    const rowAt = path.indexOf("rows")
    const field = path[path.length - 1]
    const name = String(field).replaceAll("_", " ")
    return rowAt >= 0 && typeof path[rowAt + 1] === "number"
      ? `line ${(path[rowAt + 1] as number) + 1} of the reading, value "${name}"`
      : `the reading's value "${name}"`
  }
  const places = [...new Set(issues.map((issue) => where(issue.path)))]
  return (
    `Loupe read this statement, but the review cannot show ${places.slice(0, 3).join("; ")}` +
    `${places.length > 3 ? ` and ${places.length - 3} more` : ""}. Nothing was saved or changed. ` +
    "Report this statement so the review can be fixed; reading it again will not help."
  )
}

export function statementReadingQuery(
  caseId: string,
  fileId: string,
  currency: string,
  statementId: string
) {
  return {
    queryKey: ["statement-import", caseId, fileId, currency, statementId],
    staleTime: STATEMENT_READING_FRESH_MS,
    queryFn: async () => {
      const params = new URLSearchParams({ case_id: caseId })
      if (currency) params.set("currency", currency)
      if (statementId) params.set("statement_id", statementId)
      const parsed = proposalSchema.safeParse(
        await fetchAPI(`/api/financial/statement-import/${fileId}?${params}`)
      )
      if (!parsed.success) throw Error(readingShapeMessage(parsed.error.issues))
      const data = parsed.data
      if (data.case_id !== caseId || data.evidence_file_id !== fileId)
        throw Error("The review belongs to another statement.")
      return data
    },
  }
}
