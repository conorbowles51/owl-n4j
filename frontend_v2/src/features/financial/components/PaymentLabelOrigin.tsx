import type { LedgerTransaction } from "../api"

export function PaymentLabelOrigin({
  row,
  field,
  detail = false,
}: {
  row: LedgerTransaction
  field: "from_name" | "to_name" | "category"
  detail?: boolean
}) {
  const origin = row.label_sources?.[field]
  if (origin?.source !== "description") return null
  return (
    <span
      className="block text-xs font-normal text-muted-foreground"
      title={origin.explanation}
    >
      {detail
        ? origin.explanation || "Suggested from the description."
        : "Suggested"}
    </span>
  )
}
