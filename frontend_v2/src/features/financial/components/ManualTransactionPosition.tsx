import type { StatementDraft } from "../lib/statement-review-draft"

type Anchor = StatementDraft["rows"][number]["source_order_anchor"]
export function ManualTransactionPosition({
  rowId,
  page,
  value,
  rows,
  statementPages,
  disabled,
  onChange,
}: {
  rowId: string
  page: number
  value: Anchor
  rows: {
    id: string
    page_number: number
    kind: string
    fields: Record<string, string>
  }[]
  statementPages?: number[]
  disabled?: boolean
  onChange: (anchor: Anchor) => void
}) {
  const payments = rows.filter((row) =>
    ["transaction", "unresolved"].includes(row.kind)
  )
  const candidates = payments.filter((row) => row.page_number === page)
  const pages = [
    ...new Set(
      statementPages?.length
        ? statementPages
        : rows.map((row) => row.page_number)
    ),
  ]
  const pageIndex = pages.indexOf(page)
  const previousPage = pages
    .slice(0, pageIndex)
    .reverse()
    .find((number) => payments.some((row) => row.page_number === number))
  const nextPage = pages
    .slice(pageIndex + 1)
    .find((number) => payments.some((row) => row.page_number === number))
  const previous = [...payments]
    .reverse()
    .find((row) => row.page_number === previousPage)
  const next = payments.find((row) => row.page_number === nextPage)
  const boundaries =
    !candidates.length && pageIndex >= 0
      ? [
          ...(previous ? [{ relation: "after" as const, row: previous }] : []),
          ...(next ? [{ relation: "before" as const, row: next }] : []),
        ]
      : []
  return (
    <label className="block text-sm my-2">
      Position on the printed page
      <select
        aria-label={`Printed position ${rowId}`}
        className="mt-1 block w-full min-w-0 rounded border bg-background p-2"
        disabled={disabled}
        value={value ? `${value.relation}:${value.row_id}` : ""}
        onChange={(event) => {
          const selection = event.target.value
          if (!selection) {
            onChange(null)
            return
          }
          const separator = selection.indexOf(":")
          onChange({
            relation: selection.slice(0, separator) as "before" | "after",
            row_id: selection.slice(separator + 1),
          })
        }}
      >
        <option value="">Choose where this transaction appears</option>
        {candidates.flatMap((row) =>
          (["before", "after"] as const).map((relation) => (
            <option
              key={`${relation}:${row.id}`}
              value={`${relation}:${row.id}`}
            >
              {relation === "before" ? "Before" : "After"}{" "}
              {row.fields.date || "undated row"} ·{" "}
              {(row.fields.description || "Payment reading").slice(0, 100)}
            </option>
          ))
        )}
        {boundaries.map(({ relation, row }) => (
          <option key={`${relation}:${row.id}`} value={`${relation}:${row.id}`}>
            {relation === "after"
              ? "After the last payment on"
              : "Before the first payment on"}{" "}
            page {row.page_number} · {row.fields.date || "undated row"} ·{" "}
            {(row.fields.description || "Payment reading").slice(0, 100)}
          </option>
        ))}
      </select>
      <span className="block text-xs text-muted-foreground mt-1">
        Compare the original page and choose a neighbouring printed transaction.
        This lets Loupe check running balances without guessing the order from
        dates.
        {!!boundaries.length &&
          " No payments were recognised on this page. Confirm its position beside the nearest recognised page in this statement. The payment keeps its own source page."}
        {!candidates.length &&
          !boundaries.length &&
          " No neighbouring payment is available in this statement. Keep the payment and check this page's statement assignment; opening and closing balances remain available for comparison."}
      </span>
    </label>
  )
}
