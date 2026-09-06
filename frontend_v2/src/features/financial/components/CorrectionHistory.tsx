import { z } from "zod"
import { correctionMoney } from "../lib/correction-contract"

const snapshot = z.object({
  row: z.object({
    key: z.string(),
    ref_id: z.string(),
    amount_minor: z.string().regex(/^\d+$/),
    currency: z.string(),
    direction: z.enum(["credit", "debit"]),
  }),
})
export function CorrectionHistory({
  before,
  after,
}: {
  before: unknown
  after: unknown
}) {
  const old = snapshot.safeParse(before)
  const replacement = snapshot.safeParse(after)
  if (!old.success || !replacement.success)
    return (
      <p className="text-xs">
        Correction reading history is unavailable or unrecognised.
      </p>
    )
  return (
    <details className="text-xs">
      <summary>Original and replacement readings</summary>
      <p>
        Original {old.data.row.ref_id}:{" "}
        {correctionMoney(old.data.row.amount_minor, old.data.row.currency)}{" "}
        {old.data.row.direction}
      </p>
      <p>
        Replacement {replacement.data.row.ref_id}:{" "}
        {correctionMoney(
          replacement.data.row.amount_minor,
          replacement.data.row.currency
        )}{" "}
        {replacement.data.row.direction}
      </p>
      <p>
        These are the readings recorded at this decision, not a claim about
        their current status.
      </p>
    </details>
  )
}
