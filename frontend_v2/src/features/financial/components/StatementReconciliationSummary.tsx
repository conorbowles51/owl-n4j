import { z } from "zod"
import { statementCalculation } from "../lib/statement-assessment"

export function StatementReconciliationSummary({
  calculation,
  pending,
  compact,
  format,
  controlBasis = "printed",
}: {
  calculation?: z.infer<typeof statementCalculation> | null
  pending?: boolean
  compact?: boolean
  format: (minor: string) => string
  controlBasis?: "printed" | "saved"
}) {
  if (!calculation && !pending) return null
  const liability = calculation?.balance_convention === "liability_owed"
  const controlLabel = controlBasis === "saved" ? "Saved" : "Printed"
  const difference =
    !pending && calculation?.available && calculation.difference_minor != null
      ? BigInt(calculation.difference_minor)
      : null
  const values = [
    [`${controlLabel} opening balance`, calculation?.opening_minor],
    [
      liability ? "Card payments and credits" : "Money in",
      calculation?.credit_minor,
    ],
    [
      liability ? "Card charges and debits" : "Money out",
      calculation?.debit_minor,
    ],
    ["Calculated closing balance", calculation?.calculated_closing_minor],
    [`${controlLabel} closing balance`, calculation?.printed_closing_minor],
  ]
  return (
    <section
      aria-label={
        compact
          ? "Current reconciliation while editing"
          : "Statement reconciliation calculation"
      }
      className="rounded border bg-card p-3 my-3 text-sm space-y-2"
      aria-busy={!!pending}
    >
      {!compact && <p className="font-semibold">Reconciliation</p>}
      <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {(compact ? values.slice(3) : values).map(([label, value]) => (
          <div key={label}>
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="font-medium tabular-nums">
              {pending
                ? "Checking…"
                : value == null
                  ? "Not available"
                  : format(value)}
            </dd>
          </div>
        ))}
      </dl>
      <p role="status" className="font-semibold">
        {pending
          ? "Checking your current values…"
          : difference === null
            ? "Cannot calculate the difference yet. Complete the missing or invalid values below."
            : difference === 0n
              ? "Closing balance matches. All other statement checks must also pass before import."
              : `${format((difference < 0n ? -difference : difference).toString())} ${difference < 0n ? "short of" : "above"} the ${controlBasis} closing balance.`}
      </p>
      {!compact && (
        <p className="text-muted-foreground">
          {liability
            ? "Opening amount owed + charges − payments = calculated closing amount owed."
            : "Opening balance + money in − money out = calculated closing balance."}{" "}
          A difference can come from missing or incorrect entries; compare the
          original before correcting it.
        </p>
      )}
    </section>
  )
}
