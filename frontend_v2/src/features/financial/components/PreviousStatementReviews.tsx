import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { serverStatementDraft } from "../lib/statement-review-draft"
import { formatLedgerAmount } from "../lib/ledger-format"

import { reviewRecoverySchema } from "../lib/review-recovery"

export function PreviousStatementReviews({
  caseId,
  fileId,
  recovery,
  canEdit,
  onCompared,
}: {
  caseId: string
  fileId: string
  recovery: z.infer<typeof reviewRecoverySchema>
  canEdit: boolean
  onCompared: (revision: string) => void
}) {
  const [selected, setSelected] = useState("")
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(0)
  const [checked, setChecked] = useState(false)
  const record = recovery.reviews.find((r) => r.id === selected)
  const query = useQuery({
    queryKey: ["previous-statement-review", caseId, fileId, selected, page],
    enabled: !!record,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const result = z
        .object({
          case_id: z.string(),
          evidence_file_id: z.string(),
          review_id: z.string(),
          request: z.record(z.string(), z.unknown()),
          row_count: z.number(),
          offset: z.number(),
        })
        .parse(
          await fetchAPI(
            `/api/financial/statement-import/${fileId}/previous-reviews/${selected}?case_id=${caseId}&offset=${page * 30}`
          )
        )
      if (
        result.case_id !== caseId ||
        result.evidence_file_id !== fileId ||
        result.review_id !== selected
      )
        throw Error("This saved review does not belong to the selected file.")
      return result
    },
  })
  const compare = useMutation({
    mutationFn: async () => {
      const result = z
        .object({
          case_id: z.string(),
          evidence_file_id: z.string(),
          revision: z.string(),
        })
        .parse(
          await fetchAPI(
            `/api/financial/statement-import/${fileId}/previous-reviews/compare?case_id=${caseId}`,
            {
              method: "POST",
              body: { expected_revision: recovery.revision },
            }
          )
        )
      if (
        result.case_id !== caseId ||
        result.evidence_file_id !== fileId ||
        result.revision !== recovery.revision
      )
        throw Error(
          "The comparison could not be confirmed. Reopen this statement."
        )
      return result
    },
    onSuccess: (result) => onCompared(result.revision),
  })
  const draft = serverStatementDraft(query.data?.request)
  const matching = recovery.reviews.filter((r) =>
    [r.filename, r.account, r.holder, r.period_start, r.period_end]
      .join(" ")
      .toLowerCase()
      .includes(search.toLowerCase())
  )
  const money = (value: string | null | undefined) => {
    if (!value || !record) return "Not entered"
    if (!/^-?\d+$/.test(value)) return value
    const formatted = formatLedgerAmount(value, record.currency)
    return `${formatted.text} ${formatted.currency}`
  }
  return (
    <section
      className="rounded border border-amber-400/70 bg-amber-50/40 dark:bg-amber-950/10 p-3 space-y-3 text-sm"
      aria-label="Earlier saved reviews"
    >
      <h4 className="font-semibold">
        Earlier saved reviews ({recovery.reviews.length})
      </h4>
      <p>
        Reprocessing kept the original files and saved corrections. Open an
        earlier review to compare its values with this PDF. Values are restored
        automatically only when the statement and source locations still match.
      </p>
      {recovery.unmatched_count > 0 && (
        <p>
          {recovery.unmatched_count} earlier{" "}
          {recovery.unmatched_count === 1 ? "review could" : "reviews could"}{" "}
          not be matched to the new account and period list. Check where their
          corrections belong before importing.
        </p>
      )}
      <details>
        <summary className="cursor-pointer font-medium">
          Compare earlier values
        </summary>
        <div className="space-y-3 pt-3">
          {recovery.reviews.length > 10 && (
            <label className="block">
              Find an earlier review
              <input
                className="block w-full rounded border p-2"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
          )}
          <label className="block">
            Earlier review
            <select
              aria-label="Earlier review"
              className="block w-full rounded border p-2"
              value={selected}
              onChange={(e) => {
                setSelected(e.target.value)
                setPage(0)
              }}
            >
              <option value="">Choose saved values to compare</option>
              {matching.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.account || "Account not entered"} ·{" "}
                  {r.period_start || "Period not entered"}{" "}
                  {r.period_end && `to ${r.period_end}`} · {r.origin} ·{" "}
                  {r.changed_row_count} explained changes
                  {!r.period_found ? " · Period changed" : ""} · {r.filename}
                </option>
              ))}
            </select>
          </label>
          {record && (
            <p>
              {record.filename} · {record.origin}
              {record.saved_at &&
                ` · Saved ${new Date(record.saved_at).toLocaleString()}`}
              . These values are from the earlier reading.
            </p>
          )}
          {query.isFetching && <p role="status">Opening saved values…</p>}
          {query.isError && <p role="alert">{query.error.message}</p>}
          {draft && (
            <>
              <p>
                {draft.holder} · {draft.account} · {draft.institution} ·{" "}
                {draft.periodStart} to {draft.periodEnd}
              </p>
              {draft.detailsReason && (
                <p>Account or period correction: {draft.detailsReason}</p>
              )}
              <div className="max-h-80 overflow-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Description and name</th>
                      <th>Money in</th>
                      <th>Money out</th>
                      <th>Balance</th>
                      <th>Included</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {draft.rows.map((r) => (
                      <tr key={r.id} className="border-t align-top">
                        <td className="p-2">{r.date || "Not entered"}</td>
                        <td className="p-2">
                          {r.description}
                          <span className="block text-muted-foreground">
                            {r.counterparty}
                          </span>
                        </td>
                        <td className="p-2">
                          {r.direction === "credit"
                            ? money(r.amount_minor)
                            : ""}
                        </td>
                        <td className="p-2">
                          {r.direction === "debit" ? money(r.amount_minor) : ""}
                        </td>
                        <td className="p-2">{money(r.balance_minor)}</td>
                        <td className="p-2">{r.excluded ? "No" : "Yes"}</td>
                        <td className="p-2">{r.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center gap-3">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!page}
                  onClick={() => setPage(page - 1)}
                >
                  Previous saved rows
                </Button>
                <span>
                  {page * 30 + 1} to{" "}
                  {Math.min((page + 1) * 30, query.data!.row_count)} of{" "}
                  {query.data!.row_count}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={(page + 1) * 30 >= query.data!.row_count}
                  onClick={() => setPage(page + 1)}
                >
                  Next saved rows
                </Button>
              </div>
            </>
          )}
        </div>
      </details>
      {recovery.acknowledged ? (
        <p role="status">
          Comparison saved for this file. Your current edits remain in this
          review. Save progress or confirm the import when ready.
        </p>
      ) : (
        canEdit && (
          <>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => setChecked(e.target.checked)}
              />
              I have compared the earlier saved reviews with the new reading
            </label>
            <Button
              size="sm"
              variant="outline"
              disabled={!checked || compare.isPending}
              onClick={() => compare.mutate()}
            >
              {compare.isPending
                ? "Saving comparison…"
                : "Save comparison for this file"}
            </Button>
            {compare.isError && <p role="alert">{compare.error.message}</p>}
          </>
        )
      )}
    </section>
  )
}
