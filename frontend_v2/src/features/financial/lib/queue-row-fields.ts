import type { QueueEntry } from "./review-queue"

export type Field = "currency" | "institution" | "holder" | "account_number" | "period_start" | "period_end"
export const FIELDS: [Field, string][] = [
  ["currency", "Currency"],
  ["institution", "Bank"],
  ["holder", "Account holder"],
]
// Also asked for here when the statement lacks them: the same save takes them, with the same checks.
const MISSING_FIELDS: [Field, string][] = [
  ["account_number", "Account number"],
  ["period_start", "Statement start date"],
  ["period_end", "Statement end date"],
]
const ISSUES: Record<string, Field> = { currency: "currency", institution: "institution", holder: "holder" }
export const current = (entry: QueueEntry, field: Field) => (field === "account_number" ? entry.account : entry[field]) || ""
export const fieldsFor = (entry: QueueEntry) => [...FIELDS, ...MISSING_FIELDS.filter(([field]) => !current(entry, field))]

/** True when the row should open with its fields showing: one of them is what it waits for, or is missing. */
export function needsRowDetails(entry: QueueEntry) {
  return (
    (!!entry.issue_reason && entry.issue_reason in ISSUES) ||
    !entry.currency ||
    !entry.institution ||
    !entry.holder
  )
}

/** True when the row offers its detail fields at all: the above, or an account number or date is missing. */
export function hasRowDetails(entry: QueueEntry) {
  return needsRowDetails(entry) || fieldsFor(entry).length > FIELDS.length
}
