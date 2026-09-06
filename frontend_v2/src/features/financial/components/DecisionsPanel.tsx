/**
 * The case's record of decisions, fetched.
 *
 * `DecisionsTable` draws the records it is handed. This is the half that gets
 * them, and it owns the four states a table cannot be in the middle of: no
 * case chosen, in flight, failed, and returned empty. Keeping them here is
 * what lets the table be tested against records alone. The shape follows
 * `IngestionRunsPanel` rather than departing from it, and the three places it
 * departs are below.
 *
 * **No filters and no paging controls are sent.** `useCaseDecisions(caseId)`
 * with nothing after it keys the read at `["financial-decisions", caseId,
 * null]`, and passing `{}` or an explicit undefined field would open a second
 * cache entry for identical data, the way `IngestionRunsPanel` says. The
 * consequence is that this shows the newest page at the backend's own default
 * size, which for a case with a long history is a window onto the front of the
 * log. That is why the sentence below is not optional: see the next note.
 *
 * **There is no count-disagreement warning here, and its absence is
 * deliberate.** `LedgerPanel`, `QuarantinePanel` and `IngestionRunsPanel` all
 * compare `total` against the number of rows they were sent, because their
 * endpoints do not page and so a disagreement can only mean a backend that has
 * started paging without the screen knowing. This endpoint pages by design:
 * `total` counts every decision matching the read and the page carries at most
 * `limit` of them, so `total !== decisions.length` is the ordinary case and a
 * warning would fire on every case with a history and mean nothing. What that
 * warning does on the other screens -- stop a partial list reading as a whole
 * one -- is done here by `describeDecisionPage`, which says in words which part
 * of the record is on screen and whether more follows.
 *
 * **The heading is composed by `describeDecisionPage`, not from the row
 * count.** A sentence built here from `decisions.length` would say "12
 * decisions" over the first twelve of two hundred. The format module already
 * holds the one trap that makes this hard to get right, which is that
 * `truncated` only looks forward and is false on the last page of many, so
 * "showing all of them" cannot be read off it alone.
 *
 * **An empty page is not an empty record.** `total === 0` means nothing has
 * been decided about this case, and gets the empty state. A page that came
 * back with no rows while `total` is positive means the read landed past the
 * end of the log, and it must not read as "nothing has been decided" -- it
 * gets the sentence, which says how many there are. The two call for opposite
 * next moves and `describeDecisionPage` already distinguishes them, so the
 * empty state is gated on `total` rather than on the length of the page.
 */

import { CircleAlert, Gavel, Loader2 } from "lucide-react"

import { EmptyState } from "@/components/ui/empty-state"

import { useCaseDecisions } from "../hooks/use-case-decisions"
import { describeDecisionPage } from "../lib/decision-format"
import { DecisionsTable } from "./DecisionsTable"

export function DecisionsPanel({ caseId }: { caseId: string | undefined }) {
  const { data, isPending, isError, error } = useCaseDecisions(caseId)

  if (!caseId) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="decisions-no-case">
        Choose a case to see what has been decided about its evidence.
      </p>
    )
  }

  if (isPending) {
    return (
      <div
        className="flex items-center gap-2 text-sm text-muted-foreground"
        data-testid="decisions-loading"
      >
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        Reading the record of decisions...
      </div>
    )
  }

  if (isError) {
    return (
      <div
        className="flex items-start gap-2 text-sm text-destructive"
        data-testid="decisions-error"
      >
        <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>
          The record of decisions taken on this case could not be read, so
          nothing here says why anything was set aside, hidden or removed.
          {error instanceof Error ? ` ${error.message}` : ""}
        </span>
      </div>
    )
  }

  if (data.total === 0) {
    return (
      <EmptyState
        icon={Gavel}
        title="Nothing has been decided about this case"
        description={
          "No decision has been recorded against this case's evidence. Every " +
          "row the ledger holds is there as it was read, and nothing has been " +
          "set aside, hidden behind a duplicate, or removed."
        }
      />
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground" data-testid="decisions-summary">
        {describeDecisionPage(data)}
      </p>

      <DecisionsTable decisions={data.decisions} />
    </div>
  )
}
