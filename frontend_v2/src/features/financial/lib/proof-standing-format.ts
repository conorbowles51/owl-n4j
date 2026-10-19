import { PROOF_CLASSES, type ProofStandingResponse } from "../api"

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value)
const isCount = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0
const permissions = [
  "admits_automatically",
  "requires_adjudication",
  "may_produce_ledger_rows",
  "counts_toward_totals",
] as const

/** Validate the census, without deriving permission rules from class labels. */
export function readProofStanding(
  value: unknown,
  caseId: string
): ProofStandingResponse {
  if (!isRecord(value) || value.case_id !== caseId) {
    throw new Error(
      "The evidence classification response does not identify this case."
    )
  }
  if (
    !Array.isArray(value.classes) ||
    !Array.isArray(value.counted_classes) ||
    !value.counted_classes.every((item) => typeof item === "string")
  ) {
    throw new Error("The evidence classification response is incomplete.")
  }
  const seen = new Set<string>()
  for (const row of value.classes) {
    if (
      !isRecord(row) ||
      typeof row.proof_class !== "string" ||
      !row.proof_class ||
      seen.has(row.proof_class) ||
      !isCount(row.documents) ||
      !isCount(row.transactions) ||
      !permissions.every((key) => typeof row[key] === "boolean")
    ) {
      throw new Error(
        "A classification row has missing or invalid counts or rules."
      )
    }
    seen.add(row.proof_class)
  }
  // Missing classes must never be presented as zero; keep unknown future classes visible.
  if (PROOF_CLASSES.some((member) => !seen.has(member))) {
    throw new Error(
      "The response omitted an evidence class. Missing counts cannot be treated as zero."
    )
  }
  const response = value as unknown as ProofStandingResponse
  const totals = [
    [
      response.documents,
      response.classes.reduce((sum, row) => sum + row.documents, 0),
    ],
    [
      response.transactions,
      response.classes.reduce((sum, row) => sum + row.transactions, 0),
    ],
    [
      response.documents_requiring_adjudication,
      response.classes.reduce(
        (sum, row) => sum + (row.requires_adjudication ? row.documents : 0),
        0
      ),
    ],
    [
      response.transactions_requiring_adjudication,
      response.classes.reduce(
        (sum, row) => sum + (row.requires_adjudication ? row.transactions : 0),
        0
      ),
    ],
  ]
  if (
    totals.some(
      ([reported, sum]) =>
        !isCount(reported) || !isCount(sum) || reported !== sum
    )
  ) {
    throw new Error(
      "The reported counts do not agree with the classification breakdown."
    )
  }
  const counted = new Set(response.counted_classes)
  if (
    counted.size !== response.counted_classes.length ||
    [...counted].some((member) => !seen.has(member)) ||
    response.classes.some(
      (row) => counted.has(row.proof_class) !== row.counts_toward_totals
    )
  ) {
    throw new Error(
      "The classes eligible for totals disagree with the reported rules."
    )
  }
  return response
}
