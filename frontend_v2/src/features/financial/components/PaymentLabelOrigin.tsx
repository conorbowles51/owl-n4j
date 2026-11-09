import { useRef, useState } from "react"
import type { LedgerTransaction } from "../api"
import { InlineReadingCheck } from "./InlineReadingCheck"

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

/** What Claude read before a person corrected it, kept visible next to the person's name. */
function claudeRead(explanation?: string | null) {
  return /(\S+ read: "[^"]*")/.exec(explanation || "")?.[1] ?? null
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
  if (origin?.source === "model_reading")
    return <ModelReadingMark row={row} field={field} origin={origin} detail={detail} />
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
  const read = origin.source === "investigator" ? claudeRead(origin.explanation) : null
  // "Saved by …" takes room on every payment line and says nothing about the money. Who saved a value stays in the
  // payment's detail (card, source dialog: detail), stored with the label. "Named / Confirmed / Corrected by" and
  // what Claude read first stay on the line: they say how the name came to be.
  if (origin.source === "investigator" && !detail && /^Saved by\b/.test(short))
    return read ? (
      <span className="block text-xs font-normal text-muted-foreground" title={origin.explanation} data-testid="claude-read">
        {read}
      </span>
    ) : null
  return (
    <span
      className="block text-xs font-normal text-muted-foreground"
      title={origin.explanation}
      {...(origin.source === "investigator" ? { "data-reading-row": row.key, tabIndex: -1 } : {})}
    >
      {detail
        ? origin.explanation || "Suggested from the description."
        : short}
      {read && !detail && <span className="block" data-testid="claude-read">{read}</span>}
    </span>
  )
}

/**
 * A name a model read for a person that no person has confirmed: always visible, never styled like a person's name.
 * Clicking it opens the check right under the row: the statement line, the reading with its citation, and
 * Confirm / Correct / Cancel. Closing it puts focus back on this label.
 */
function ModelReadingMark({
  row,
  field,
  origin,
  detail,
}: {
  row: LedgerTransaction
  field: "from_name" | "to_name" | "category"
  origin: NonNullable<NonNullable<LedgerTransaction["label_sources"]>["to_name"]>
  detail: boolean
}) {
  const [open, setOpen] = useState(detail)
  const trigger = useRef<HTMLButtonElement>(null)
  const label =
    origin.label || `Read by ${origin.origin?.model || "a model"} · not confirmed`
  const checkable = field !== "category"
  return (
    <span className="block text-xs font-normal" data-reading-row={row.key}>
      <button
        ref={trigger}
        type="button"
        className="rounded border border-status-warning bg-status-warning-soft px-1 text-status-warning hover:underline"
        title={origin.explanation}
        aria-expanded={open}
        data-testid="model-reading-mark"
        onClick={(event) => {
          event.stopPropagation()
          setOpen((value) => !value)
        }}
      >
        {label}
        {checkable && <span> — click to check</span>}
      </button>
      {open && checkable && (
        <InlineReadingCheck
          row={row}
          field={field}
          citation={origin.explanation}
          onDone={() => {
            setOpen(false)
            // The row may have re-rendered: put focus on whichever label is on this row now.
            requestAnimationFrame(() =>
              (trigger.current?.isConnected
                ? trigger.current
                : document.querySelector<HTMLElement>(`[data-reading-row="${CSS.escape(row.key)}"][tabindex]`)
              )?.focus({ preventScroll: true })
            )
          }}
        />
      )}
      {open && !checkable && origin.explanation && (
        <span className="mt-0.5 block text-muted-foreground">{origin.explanation}</span>
      )}
    </span>
  )
}
