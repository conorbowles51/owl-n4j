import { useState } from "react"
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
  if (origin?.source === "model_reading") return <ModelReadingMark origin={origin} detail={detail} />
  if (origin?.source === "investigator" && origin.confirmed_model_reading && detail)
    return (
      <span className="block text-xs font-normal text-muted-foreground">
        {origin.explanation}
      </span>
    )
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

/**
 * A name a model read for a person that no person has confirmed: always visible, never styled like a person's name.
 * The citation (what it was read from, when, for whom) shows on hover and opens on click.
 */
function ModelReadingMark({
  origin,
  detail,
}: {
  origin: NonNullable<NonNullable<LedgerTransaction["label_sources"]>["to_name"]>
  detail: boolean
}) {
  const [open, setOpen] = useState(detail)
  const label =
    origin.label || `Read by ${origin.origin?.model || "a model"} · not confirmed`
  return (
    <span className="block text-xs font-normal">
      <button
        type="button"
        className="rounded border border-[#e7c66b] bg-[#fdf6dd] px-1 text-[#7a5200] hover:underline dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200"
        title={origin.explanation}
        aria-expanded={open}
        data-testid="model-reading-mark"
        onClick={(event) => {
          event.stopPropagation()
          setOpen((value) => !value)
        }}
      >
        {label}
      </button>
      {open && origin.explanation && (
        <span className="mt-0.5 block text-muted-foreground">{origin.explanation}</span>
      )}
    </span>
  )
}
