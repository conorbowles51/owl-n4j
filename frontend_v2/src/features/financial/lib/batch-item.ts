import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { statementAssessment } from "./statement-assessment"
import { statementDuplicateDisposition } from "./statement-duplicate"
import { coverageReview } from "../hooks/use-statement-coverage-review"

export const itemSchema = z.object({
  id: z.string(),
  file_id: z.string(),
  statement_id: z.string().nullish(),
  status: z.string(),
  filename: z.string(),
  currency: z.string().optional(),
  holder: z.string().optional(),
  account: z.string().optional(),
  period_start: z.string().optional(),
  period_end: z.string().optional(),
  transaction_count: z.number(),
  record_count: z.number().optional(),
  incomplete_count: z.number().optional(),
  unclassified_count: z.number().optional(),
  problem_count: z.number().optional(),
  can_import: z.boolean().optional(),
  admission: statementAssessment.nullish(),
  duplicate_disposition: statementDuplicateDisposition.nullish(),
  balance_status: z.string().optional(),
  balance_exception: z.boolean().optional(),
  /** The latest page-image outcome; with rule 2, a reading that checks out offered beside the person's work. */
  vision_reading: z
    .object({
      status: z.string().nullish(),
      line: z.string().nullish(),
      offer: z.object({ id: z.string(), mine: z.record(z.string(), z.unknown()), offered: z.record(z.string(), z.unknown()) }).nullish(),
    })
    .nullish(),
  source_id: z.string(),
  review_revision: z.string().optional(),
  disposition_revision: z.string().optional(),
  coverage_review: coverageReview.optional(),
  import_decision: z
    .object({ action: z.string(), reason: z.string() })
    .optional(),
  review_request: z.record(z.string(), z.unknown()).nullish(),
  problems: z.array(
    z.object({
      message: z.string(),
      row_id: z.string().nullish(),
      page: z.number().nullish(),
      field: z.string().optional(),
      kind: z.string().optional(),
      review_reason: z.string().optional(),
    })
  ),
})

/** One batch statement as its review opens it. Shared so the review queue can
 * load the next statement in the background: Next then shows it at once. */
export const BATCH_ITEM_FRESH_MS = 120_000
export function batchItemQuery(caseId: string, batchId: string, itemId: string) {
  return {
    queryKey: ["financial-batch-item", caseId, batchId, itemId],
    queryFn: async () =>
      itemSchema
        .extend({ review_revision: z.string() })
        .parse(
          await fetchAPI(
            `/api/financial/statement-import/batches/${batchId}/items/${itemId}?case_id=${caseId}`
          )
        ),
    staleTime: BATCH_ITEM_FRESH_MS,
  }
}
