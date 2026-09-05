/**
 * The relational ledger, fetched.
 *
 * `LedgerTable` draws rows it is handed. This is the half that gets them, and
 * it owns the four states a table cannot be in the middle of: no case chosen,
 * in flight, failed, and returned empty. Keeping them here is what lets the
 * table be tested against rows alone.
 *
 * **The empty case carries most of the weight.** The ledger read defaults to
 * `admitted` — verified in `list_transactions`, which substitutes
 * `LedgerStatus.admitted` when no status is passed, rather than returning
 * every row regardless of status. So zero rows does not mean the case has no
 * financial material. It means nothing in the relational ledger holds this
 * status, and rows that were quarantined, superseded or rejected are sitting
 * outside the filter, uncounted and unshown. An empty state that said "no
 * transactions" would state the opposite of what was checked. This one names
 * the status it filtered on and says where the rest would be.
 *
 * **The count comes from the rows, not from `total`.** The endpoint returns
 * `total` as `len(transactions)` of the same response: there is no paging
 * behind it. Reading a count from `total` would therefore be reading a number
 * that means "how many are in front of you" while implying "how many exist".
 * The two are compared instead, and a disagreement is surfaced, because the
 * only way they can differ is a backend that has started paging without this
 * screen knowing — at which point every figure derived from a page is a
 * figure over a subset.
 */

import { CircleAlert, Loader2, ScrollText } from "lucide-react"

import { EmptyState } from "@/components/ui/empty-state"

import { useLedgerTransactions, type LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { readLedgerStatus } from "../lib/ledger-format"
import { LedgerTable } from "./LedgerTable"

/** The endpoint's default when no status is sent. See the module docstring. */
const DEFAULT_LEDGER_STATUS = "admitted"

export function LedgerPanel({
  caseId,
  params,
}: {
  caseId: string | undefined
  params?: LedgerQueryParams
}) {
  const { data, isPending, isError, error } = useLedgerTransactions(caseId, params)

  if (!caseId) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="ledger-no-case">
        Choose a case to read its ledger.
      </p>
    )
  }

  if (isPending) {
    return (
      <div
        className="flex items-center gap-2 text-sm text-muted-foreground"
        data-testid="ledger-loading"
      >
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        Reading the ledger...
      </div>
    )
  }

  if (isError) {
    return (
      <div
        className="flex items-start gap-2 text-sm text-destructive"
        data-testid="ledger-error"
      >
        <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>
          The ledger could not be read, so nothing below is a count of anything.
          {error instanceof Error ? ` ${error.message}` : ""}
        </span>
      </div>
    )
  }

  const status = readLedgerStatus(params?.ledgerStatus ?? DEFAULT_LEDGER_STATUS)
  const rows = data.transactions
  const countDisagrees = data.total !== rows.length

  if (rows.length === 0) {
    return (
      <EmptyState
        icon={ScrollText}
        title={`No ${status.label.toLowerCase()} rows in the ledger`}
        description={
          `Nothing in this case's relational ledger currently holds the ` +
          `status "${status.label.toLowerCase()}". Rows that were quarantined, ` +
          `superseded or rejected are not counted here and are not shown; ` +
          `change the status filter to see them.`
        }
      />
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground" data-testid="ledger-summary">
        {rows.length} {rows.length === 1 ? "row" : "rows"}, {status.label.toLowerCase()}.
      </p>

      {countDisagrees && (
        <p
          className="flex items-start gap-2 text-xs text-destructive"
          data-testid="ledger-count-disagreement"
        >
          <CircleAlert className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
          <span>
            The ledger reported {data.total} rows and sent {rows.length}. Treat
            what is below as part of the answer, not all of it.
          </span>
        </p>
      )}

      <LedgerTable transactions={rows} />
    </div>
  )
}
