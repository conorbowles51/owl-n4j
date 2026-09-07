import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"

const id = z.string().min(1)
const revision = z.string().regex(/^[a-f0-9]{64}$/)
export const candidateStatus = z.enum(["pending", "resolved", "rejected"])
export const candidateReading = z.object({
  account_id: id,
  currency: z.string().regex(/^[A-Z]{3}$/),
  amount_minor: z
    .string()
    .regex(/^(0|[1-9][0-9]{0,18})$/)
    .refine((v) => BigInt(v) <= 9223372036854775807n),
  direction: z.enum(["credit", "debit"]),
  booking_date: z.string().nullable(),
  value_date: z.string().nullable(),
  transaction_date: z.string().nullable(),
  description: z.string(),
})
const original = z.object({
  cells: z.array(
    z
      .object({
        column_index: z.number().int().nonnegative(),
        proposed_meaning: z.string(),
        text: z.string().optional(),
        source: z.object({ text: z.string() }).optional(),
      })
      .refine(
        (v) => typeof v.text === "string" || typeof v.source?.text === "string"
      )
  ),
})
const history = z.array(
  z.object({
    id,
    sequence: z.number().int().positive(),
    status: candidateStatus,
    reason: z.string(),
    reading: candidateReading.nullable(),
    actor: z.object({ name: z.string(), email: z.string() }),
    created_at: z.string(),
  })
)
export const candidateReview = z
  .object({
    candidate_id: id,
    case_id: id,
    original,
    status: candidateStatus,
    reading: candidateReading.nullable(),
    review_revision: revision,
    history,
    applied: z.literal(false),
  })
  .refine(
    (v) => (v.status === "resolved") === (v.reading !== null),
    "Inconsistent candidate review"
  )
export type CandidateReview = z.infer<typeof candidateReview>
export type CandidateReading = z.infer<typeof candidateReading>
export const candidateMapping = z.object({
  id,
  case_id: id,
  evidence_file_id: id,
  mapping_revision: revision,
  applied: z.literal(false),
  original: z.object({
    proposal: z.object({ case_id: id, evidence_file_id: id }),
  }),
  candidates: z.array(
    z.object({
      id,
      row_index: z.number().int().nonnegative(),
      status: candidateStatus,
      original,
    })
  ),
})
export const candidateList = z.object({
  case_id: id,
  offset: z.number().int().nonnegative(),
  has_more: z.boolean(),
  items: z.array(
    z.object({
      id,
      evidence_file_id: id,
      filename: z.string(),
      candidate_count: z.number().int().positive(),
      created_at: z.string(),
    })
  ),
})
export const candidateAccounts = z.object({
  case_id: id,
  has_more: z.boolean(),
  items: z.array(
    z.object({
      id,
      identifier: z.string().nullable(),
      holder: z.string().nullable(),
      institution: z.string().nullable(),
      currency: z.string().nullable(),
    })
  ),
})
export const candidateAssessment = z.object({
  case_id: id,
  candidate_id: id,
  mapping_id: id,
  currency: z.string(),
  review_revision: revision,
  assessment_revision: revision,
  applied: z.literal(false),
  amount_cells: z.array(
    z.object({
      column_index: z.number().int().nonnegative(),
      proposed_meaning: z.string(),
      source: z.object({
        text: z.string(),
        locator: z.unknown().optional(),
        page_number: z.number().int().positive().nullable().optional(),
      }),
      assessment: z
        .object({
          raw: z.string(),
          origin: z.string(),
          explanation: z.string(),
          minor_units: z
            .string()
            .regex(/^-?[0-9]+$/)
            .optional(),
          proposals: z
            .array(
              z.object({
                minor_units: z.string().regex(/^-?[0-9]+$/),
                basis: z.string(),
              })
            )
            .optional(),
        })
        .nullable(),
      error: z.string().nullable(),
    })
  ),
  unclassified_columns: z.array(z.number().int().nonnegative()),
})

export function candidateUrl(path: string, caseId: string) {
  return `/api/financial/${path}?${new URLSearchParams({ case_id: caseId })}`
}
export function assertCandidateScope(
  value: { case_id: string },
  caseId: string
) {
  if (value.case_id !== caseId)
    throw new Error(
      "The response belongs to a different case. Reload before reviewing."
    )
}
export async function fetchCandidateReview(
  caseId: string,
  candidateId: string
) {
  const result = candidateReview.parse(
    await fetchAPI<unknown>(
      candidateUrl(
        `candidates/${encodeURIComponent(candidateId)}/review`,
        caseId
      )
    )
  )
  assertCandidateScope(result, caseId)
  if (result.candidate_id !== candidateId)
    throw new Error("The review belongs to a different reading.")
  return result
}
