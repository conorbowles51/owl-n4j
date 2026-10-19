/**
 * The record of every attempt to load evidence into the ledger, fetched.
 *
 * `IngestionRunsTable` draws the attempts it is handed. This is the half that
 * gets them, and it owns the four states a table cannot be in the middle of: no
 * case chosen, in flight, failed, and returned empty. Keeping them here is what
 * lets the table be tested against runs alone.
 *
 * **This read returns every status, and must not be narrowed.** `/runs`
 * defaults to all of them, `failed` and `aborted` included — the opposite of
 * the ledger read, which defaults to `admitted`. The failures are the payload:
 * a list filtered to the attempts that finished would answer "what worked"
 * while appearing to answer "what happened". So no status parameter is sent.
 *
 * **No limit is sent either.** Passing `useIngestionRuns(caseId)` with nothing
 * after it is what makes this share a single fetch and a single cache entry —
 * `["financial-runs", caseId, null]` — with `IngestionRunNotice`. Adding `{}`
 * or an explicit undefined field would open a second entry and a second request
 * for identical data.
 *
 * **The count comes from the rows, not from `total`.** The endpoint returns
 * `total` as `len(runs)` of the same response; there is no paging behind it.
 * The two are compared and a disagreement is surfaced, because the only way
 * they can differ is a backend that has started paging without this screen
 * knowing, at which point a history that looks complete is a window onto part
 * of one. Same reasoning, and the same treatment, as `LedgerPanel`.
 *
 * **The empty case claims nothing about the ledger.** No recorded attempt is a
 * fact about this record, not evidence that the ledger is empty or that it is
 * full, so the empty state says only what this screen does and does not hold.
 */

import { CircleAlert, History, Loader2 } from "lucide-react"

import { EmptyState } from "@/components/ui/empty-state"

import { useIngestionRuns } from "../hooks/use-ingestion-runs"
import { IngestionRunsTable } from "./IngestionRunsTable"

export function IngestionRunsPanel({ caseId }: { caseId: string | undefined }) {
  const { data, isPending, isError, error } = useIngestionRuns(caseId)

  if (!caseId) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="runs-no-case">
        Choose a case to see what has been loaded into its ledger.
      </p>
    )
  }

  if (isPending) {
    return (
      <div
        className="flex items-center gap-2 text-sm text-muted-foreground"
        data-testid="runs-loading"
      >
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        Reading the record of past attempts...
      </div>
    )
  }

  if (isError) {
    return (
      <div
        className="flex items-start gap-2 text-sm text-destructive"
        data-testid="runs-error"
      >
        <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>
          The record of attempts to load this ledger could not be read, so
          nothing here says what the ledger was built from.
          {error instanceof Error ? ` ${error.message}` : ""}
        </span>
      </div>
    )
  }

  const runs = data.runs
  const countDisagrees = data.total !== runs.length

  if (runs.length === 0) {
    return (
      <EmptyState
        icon={History}
        title="No attempts recorded against this case"
        description={
          "Nothing has been recorded here as an attempt to load evidence into " +
          "this case's ledger. If the ledger holds rows, this screen has no " +
          "record of what put them there."
        }
      />
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground" data-testid="runs-summary">
        {runs.length} {runs.length === 1 ? "attempt" : "attempts"}, newest first.
      </p>

      {countDisagrees && (
        <p
          className="flex items-start gap-2 text-xs text-destructive"
          data-testid="runs-count-disagreement"
        >
          <CircleAlert className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
          <span>
            The record reported {data.total} attempts and sent {runs.length}.
            Treat what is below as part of the history, not all of it.
          </span>
        </p>
      )}

      <IngestionRunsTable runs={runs} />
    </div>
  )
}
