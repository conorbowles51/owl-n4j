import type { LedgerTransaction } from "../api"

const SHORT: Record<string, string> = {
  description: "Auto",
  model: "Model guess",
  learned: "Learned",
}

/** A quiet note of who set an automatic label: rules, the model, or a person's choice applied to similar payments. */
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
  if (!origin || !SHORT[origin.source]) return null
  const short =
    origin.source === "description" && field !== "category"
      ? "Suggested"
      : SHORT[origin.source]
  return (
    <span
      className="block text-xs font-normal text-muted-foreground"
      title={origin.explanation}
    >
      {detail
        ? origin.explanation || "Suggested from the description."
        : short}
    </span>
  )
}
