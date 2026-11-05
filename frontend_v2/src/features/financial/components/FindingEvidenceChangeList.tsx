import { Button } from "@/components/ui/button"
import type {
  CitedPaymentChange,
  FindingEvidenceChanges,
} from "@/features/workspace/casework-api"
import { formatLedgerAmount } from "../lib/ledger-format"

const stateText: Record<CitedPaymentChange["state"], string> = {
  changed: "Changed",
  corrected: "Corrected by a later version",
  set_aside: "No longer counted in Transactions",
  missing: "No longer in this case",
}

function shown(
  change: CitedPaymentChange["changes"][number],
  value: string | null | undefined,
  currency: string | undefined
) {
  if (value == null) return "not recorded"
  if (change.field === "amount_minor" && currency)
    return `${formatLedgerAmount(value, currency).text} ${currency}`
  return value
}

/** What changed since citing. The saved citation below it is unchanged, and stays what the finding cites. */
export function FindingEvidenceChangeList({
  evidence,
  onOpen,
}: {
  evidence: FindingEvidenceChanges["entries"][string]
  onOpen: (id: string) => void
}) {
  if (!evidence.changed.length && !evidence.not_compared) return null
  return (
    <section
      className="finance-tint rounded border p-3 space-y-2 text-sm"
      data-finance-tone="review"
      aria-label="Changes to cited evidence"
    >
      {evidence.changed.length > 0 && (
        <>
          <h4 className="font-medium">Changed since cited</h4>
          <p>
            This finding still shows the values it cited. They are not updated
            here.
          </p>
          <ul className="space-y-2">
            {evidence.changed.map((item) => (
              <li key={item.transaction_id}>
                <p>
                  {item.ref_id || "Payment"}: {stateText[item.state]}
                </p>
                {item.changes.map((change) => (
                  <p key={change.field} className="break-words">
                    {change.label}: cited{" "}
                    {shown(change, change.cited, item.currency)}, now{" "}
                    {shown(change, change.current, item.currency)}
                    {change.reading ? ` (${change.reading})` : ""}
                  </p>
                ))}
                {item.current_id && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onOpen(item.current_id!)}
                  >
                    Open current payment
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {evidence.not_compared > 0 && (
        <p>
          {evidence.not_compared} cited{" "}
          {evidence.not_compared === 1 ? "payment has" : "payments have"} no
          saved values to compare.
        </p>
      )}
    </section>
  )
}
