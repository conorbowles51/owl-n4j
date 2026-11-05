import { ApiError } from "@/lib/api-client"

/** A review as saved to the case, read fresh after a refused save. */
export interface SavedReview {
  review_revision: string
  saved_at?: string | null
  saved_by?: {
    name?: string | null
    origin?: Record<string, unknown> | null
  } | null
  request: Record<string, unknown>
}

export interface ReviewDifference {
  key: string
  label: string
  saved: string
  local: string
}

/** Refused because someone saved first, as opposed to any other refusal, which has nothing to compare. */
export const isReviewConflict = (error: unknown) =>
  error instanceof ApiError &&
  error.status === 409 &&
  /^Another (?:reviewer|user) saved/.test(error.message)

const statementFields = [
  ["holder", "Account holder"],
  ["institution", "Bank"],
  ["account_number", "Account number"],
  ["period_start", "Period start"],
  ["period_end", "Period end"],
  ["details_reason", "Reason for details"],
  ["coverage_review_reason", "Coverage note"],
  ["balance_exception_reason", "Balance note"],
  ["no_activity_confirmed", "No activity confirmed"],
] as const
const rowFields = [
  ["date", "date"],
  ["description", "description"],
  ["counterparty", "other party"],
  ["amount_minor", "amount"],
  ["direction", "direction"],
  ["balance_minor", "balance"],
  ["excluded", "excluded"],
  ["reason", "reason"],
] as const

const shown = (value: unknown) =>
  value === undefined || value === null || value === ""
    ? "Blank"
    : value === true
      ? "Yes"
      : value === false
        ? "No"
        : String(value)

type Row = Record<string, unknown> & { id: string }
const rowsOf = (request: Record<string, unknown>) =>
  new Map(
    (Array.isArray(request.rows) ? (request.rows as Row[]) : []).map((row) => [
      row.id,
      row,
    ])
  )

/** Every difference between the saved review and this person's unsaved values, statement fields first. */
export function reviewDifferences(
  saved: Record<string, unknown>,
  local: Record<string, unknown>
): ReviewDifference[] {
  const differences: ReviewDifference[] = []
  for (const [field, label] of statementFields)
    if (shown(saved[field]) !== shown(local[field]))
      differences.push({
        key: field,
        label,
        saved: shown(saved[field]),
        local: shown(local[field]),
      })
  const savedRows = rowsOf(saved)
  const localRows = rowsOf(local)
  for (const id of new Set([...savedRows.keys(), ...localRows.keys()])) {
    const before = savedRows.get(id)
    const after = localRows.get(id)
    const name = String(after?.description || before?.description || id)
    if (!before || !after) {
      differences.push({
        key: `${id}:presence`,
        label: `Payment ${name}`,
        saved: before ? "Present" : "Not in this version",
        local: after ? "Present" : "Not in this version",
      })
      continue
    }
    for (const [field, label] of rowFields)
      if (shown(before[field]) !== shown(after[field]))
        differences.push({
          key: `${id}:${field}`,
          label: `Payment ${name}: ${label}`,
          saved: shown(before[field]),
          local: shown(after[field]),
        })
  }
  return differences
}
