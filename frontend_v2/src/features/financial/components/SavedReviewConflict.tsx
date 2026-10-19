import { useState } from "react"
import { Button } from "@/components/ui/button"
import type { StatementDraft } from "../lib/statement-review-draft"

export function SavedReviewConflict({
  draft,
  checked,
  onChecked,
  formatAmount,
}: {
  draft: StatementDraft
  checked: boolean
  onChecked: (checked: boolean) => void
  formatAmount: (value: string) => string
}) {
  const [page, setPage] = useState(0)
  const rows = draft.rows.filter((row) => row.reason || !row.excluded)
  const size = 30
  return (
    <section
      className="rounded border border-amber-500 p-3 my-3 space-y-2 text-sm"
      aria-label="Previous saved review"
    >
      <h4 className="font-semibold">
        The reading changed after this review was saved
      </h4>
      <p>
        Your previous saved values are retained below. They have not been copied
        to the new reading because its rows may be different. Compare any
        corrections before importing.
      </p>
      <details>
        <summary className="cursor-pointer">
          Show previous saved values ({rows.length} rows)
        </summary>
        <p className="my-2">
          {draft.holder} · {draft.account} · {draft.periodStart} to{" "}
          {draft.periodEnd}
        </p>
        {draft.detailsReason && (
          <p>Earlier explanation: {draft.detailsReason}</p>
        )}
        <div className="max-h-64 overflow-auto">
          <table className="w-full text-left">
            <thead>
              <tr>
                <th>Date</th>
                <th>Description</th>
                <th>Amount</th>
                <th>Included</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(page * size, (page + 1) * size).map((row) => (
                <tr key={row.id} className="border-t">
                  <td className="p-2">{row.date}</td>
                  <td className="p-2">{row.description}</td>
                  <td className="p-2">
                    {formatAmount(row.amount_minor)} {row.direction}
                  </td>
                  <td className="p-2">{row.excluded ? "No" : "Yes"}</td>
                  <td className="p-2">{row.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length > size && (
          <div className="flex gap-2 mt-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!page}
              onClick={() => setPage(page - 1)}
            >
              Previous saved rows
            </Button>
            <span>
              {page * size + 1} to {Math.min(rows.length, (page + 1) * size)} of{" "}
              {rows.length}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={(page + 1) * size >= rows.length}
              onClick={() => setPage(page + 1)}
            >
              Next saved rows
            </Button>
          </div>
        )}
      </details>
      <label className="flex gap-2 items-center">
        <input
          type="checkbox"
          aria-label="I have compared the previous saved review"
          checked={checked}
          onChange={(event) => onChecked(event.target.checked)}
        />
        I have compared the previous saved review
      </label>
    </section>
  )
}
