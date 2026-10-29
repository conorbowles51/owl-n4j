import type { LedgerTransaction } from "../api"

const SHORT: Record<string, string> = {
  description: "Auto",
  model: "Model guess",
  learned: "Learned",
  matched_payment: "Matched payment",
  printed_account: "Account printed on the line",
  investigator: "Saved by a person",
}

/** A person's label, shortened to who set it: "Named by Ana from the statement", "Saved by Ana". */
function personShort(explanation?: string | null) {
  const text = (explanation || "")
    .replace(/ on \d{4}-\d{2}-\d{2}[\s\S]*$/, "")
    .replace(/ to an existing [\s\S]*$/, "")
    .replace(/\.$/, "")
  return text || SHORT.investigator
}

/** A quiet note of who set a label: rules, the model, a person's choice applied to similar payments, or the person. */
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
  if (origin?.source === "missing" && origin.reason && detail)
    return (
      <span className="block text-xs font-normal text-muted-foreground">
        {origin.explanation}
      </span>
    )
  if (!origin || !SHORT[origin.source]) return null
  const short =
    origin.source === "investigator"
      ? personShort(origin.explanation)
      : origin.source === "description" && field !== "category"
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
