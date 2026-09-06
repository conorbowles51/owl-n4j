/**
 * The rows held out of every total, fetched.
 *
 * The read is the ordinary ledger read with `ledger_status=quarantined`; there
 * is no endpoint of its own and none is needed. What is different is what the
 * screen can truthfully say, which is why this is a component rather than
 * `<LedgerPanel params={{ ledgerStatus: "quarantined" }} />`.
 *
 * **The empty state means the opposite thing here.** `LedgerPanel` tells a
 * reader that quarantined, superseded and rejected rows are sitting outside
 * the filter, uncounted. Pointed at a quarantined list that sentence states
 * the reverse of what was checked: quarantined rows are not outside this
 * filter, they are the whole of it. Zero rows here means no rows are currently
 * quarantined; classification and document status can still exclude evidence.
 *
 * **The status is not the caller's to choose.** It is fixed rather than
 * defaulted, so no caller can pass `admitted` into a panel whose every
 * sentence is about quarantine. The remaining filters are still the caller's.
 *
 * **The count comes from the rows, not from `total`.** Same reasoning as
 * `LedgerPanel`: the endpoint returns `total` as `len(transactions)` of the
 * same response, so a disagreement between the two can only mean the backend
 * has started paging without this screen knowing, and a page of quarantined
 * rows presented as the whole set is an undercount of what is being excluded.
 *
 * **The words behind an adjudicated hold are not on this screen.** The ledger
 * read carries `quarantine_reason` and no detail field: the actor-and-reason
 * text a person gives is written to the adjudication record, which this does
 * not read. So the panel says where the reasoning is rather than leaving a
 * reader to conclude there was none.
 */

import { CircleAlert, Loader2, ShieldCheck } from "lucide-react"

import { EmptyState } from "@/components/ui/empty-state"

import type { LedgerTransaction } from "../api"
import {
  useLedgerTransactions,
  type LedgerQueryParams,
} from "../hooks/use-ledger-transactions"
import { LedgerTable } from "./LedgerTable"

/** Fixed, not defaulted. See the module docstring. */
const QUARANTINED = "quarantined" as const

export function QuarantinePanel({
  caseId,
  params,
  onAdjudicate,
  onCorrect,
}: {
  caseId: string | undefined
  params?: Omit<LedgerQueryParams, "ledgerStatus">
  /**
   * Passed straight to the table, which draws the action column when it is
   * given. This panel does not hold the dialog, and here the reason is at its
   * sharpest: letting the last held row back in empties this list, so the
   * "no rows are currently quarantined" state above returns and everything below it
   * is unmounted. A dialog owned here would go with it, taking the answer to
   * the change, which is said in that one response and nowhere else.
   */
  onAdjudicate?: (transaction: LedgerTransaction) => void
  onCorrect?: (transaction: LedgerTransaction) => void
}) {
  const { data, isPending, isError, error } = useLedgerTransactions(caseId, {
    ...params,
    ledgerStatus: QUARANTINED,
  })

  if (!caseId) {
    return (
      <p
        className="text-sm text-muted-foreground"
        data-testid="quarantine-no-case"
      >
        Choose a case to see what is being held out of its totals.
      </p>
    )
  }

  if (isPending) {
    return (
      <div
        className="flex items-center gap-2 text-sm text-muted-foreground"
        data-testid="quarantine-loading"
      >
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        Reading the quarantined rows...
      </div>
    )
  }

  if (isError) {
    return (
      <div
        className="flex items-start gap-2 text-sm text-destructive"
        data-testid="quarantine-error"
      >
        <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>
          The quarantined rows could not be read, so nothing below is a count of
          what is being excluded.
          {error instanceof Error ? ` ${error.message}` : ""}
        </span>
      </div>
    )
  }

  const rows = data.transactions
  const countDisagrees = data.total !== rows.length

  if (rows.length === 0) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title="No rows are currently quarantined"
        description={
          "No row in this case's relational ledger is currently quarantined, " +
          "but evidence classification and document status still determine inclusion in totals. Rows that " +
          "were superseded or rejected are a separate matter and are not " +
          "shown here."
        }
      />
    )
  }

  return (
    <div className="space-y-3">
      <p
        className="text-xs text-muted-foreground"
        data-testid="quarantine-summary"
      >
        {rows.length} {rows.length === 1 ? "row" : "rows"} held out of every
        total in this case.
      </p>

      <p
        className="text-xs text-muted-foreground"
        data-testid="quarantine-adjudication-note"
      >
        Where a row was set aside by a person, what they gave as their reason is
        on the record of that decision and is not repeated here.
      </p>

      {countDisagrees && (
        <p
          className="flex items-start gap-2 text-xs text-destructive"
          data-testid="quarantine-count-disagreement"
        >
          <CircleAlert className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
          <span>
            The ledger reported {data.total} quarantined rows and sent{" "}
            {rows.length}. More is being held out of the totals than is shown
            below.
          </span>
        </p>
      )}

      <LedgerTable
        transactions={rows}
        showQuarantineGrounds
        onAdjudicate={onAdjudicate}
        onCorrect={onCorrect}
      />
    </div>
  )
}
