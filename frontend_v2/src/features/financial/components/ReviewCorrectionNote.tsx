import { formatLedgerAmount } from "../lib/ledger-format"

/**
 * A payment whose amount, direction or date a person changed in the statement review before import. The value read
 * stays visible beside the saved value, and the note says which one is used: only the saved value counts in sums,
 * flows and searches.
 */
export type ReviewCorrection = {
  changes: { field: "amount" | "direction" | "date"; read: string; saved: string }[]
  reason?: string | null
}

const FIELD = { amount: "Amount", direction: "Direction", date: "Date" } as const
const DIRECTION: Record<string, string> = { credit: "money in", debit: "money out" }

function shown(field: ReviewCorrection["changes"][number]["field"], value: string, currency: string) {
  if (field === "amount") {
    const amount = formatLedgerAmount(value, currency)
    return `${amount.text} ${amount.currency}`.trim()
  }
  if (field === "direction") return DIRECTION[value] ?? value
  return value
}

export function ReviewCorrectionNote({
  correction,
  currency,
}: {
  correction?: ReviewCorrection
  currency: string
}) {
  if (!correction?.changes?.length) return null
  return (
    <div
      role="note"
      aria-label="Corrected before import"
      data-testid="review-correction"
      className="mt-1 space-y-0.5 rounded border border-[#9fb7e8] bg-[#eef3fd] px-2 py-1 text-[12px] text-[#1d3a75] dark:bg-blue-950/40 dark:text-blue-200"
    >
      <p className="font-semibold">Corrected before import. The corrected value is the one used.</p>
      {correction.changes.map((change) => (
        <p key={change.field}>
          {FIELD[change.field]}: read as <span className="font-mono line-through">{shown(change.field, change.read, currency)}</span>
          {", corrected to "}
          <span className="font-mono font-semibold">{shown(change.field, change.saved, currency)}</span>
        </p>
      ))}
      {correction.reason && <p className="text-muted-foreground">Reason: {correction.reason}</p>}
    </div>
  )
}
