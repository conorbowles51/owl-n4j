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

import { useState } from "react"
import { CircleAlert, Loader2, ScrollText } from "lucide-react"

import { EmptyState } from "@/components/ui/empty-state"

import type { LedgerTransaction } from "../api"
import {
  useLedgerTransactions,
  type LedgerQueryParams,
} from "../hooks/use-ledger-transactions"
import { useLedgerCount } from "../hooks/use-ledger-count"
import { readLedgerStatus } from "../lib/ledger-format"
import { useElapsedSeconds } from "../lib/request-wait"
import { LedgerRowBrowser } from "./LedgerRowBrowser"
import { WorkspaceScope } from "./InvestigationWorkspaceParts"

/** The endpoint's default when no status is sent. See the module docstring. */
const DEFAULT_LEDGER_STATUS = "admitted"

export function LedgerPanel({
  caseId,
  params,
  onAdjudicate,
  onCorrect,
  onSource,
  onNote,
  splitAmounts = false,
  investigation = false,
  independentFilters = false,
}: {
  caseId: string | undefined
  params?: LedgerQueryParams
  /**
   * Passed straight to the table, which draws the action column when it is
   * given. This panel does not hold the dialog: a successful change empties
   * the list this panel is reading, and the empty state above returns before
   * anything below it renders, so a dialog owned here would be torn down at
   * the moment its answer arrived.
   */
  onAdjudicate?: (transaction: LedgerTransaction) => void
  onCorrect?: (transaction: LedgerTransaction) => void
  onSource?: (transaction: LedgerTransaction) => void
  onNote?: (transaction: LedgerTransaction) => void
  splitAmounts?: boolean
  investigation?: boolean
  independentFilters?: boolean
}) {
  // The Transactions page first shows what the server works out for its default view (one page of rows and the
  // figures above them) and reads every payment only when the person asks for something that needs them all, or
  // once the page has settled (LedgerRowBrowser). Elsewhere, and for other statuses, every row is read as before.
  const firstViewMode =
    !!caseId &&
    investigation &&
    !independentFilters &&
    (params?.ledgerStatus ?? DEFAULT_LEDGER_STATUS) === "admitted"
  const scopeKey = JSON.stringify([caseId, params ?? null])
  const [wanted, setWanted] = useState<string | null>(null)
  const wantAll = !firstViewMode || wanted === scopeKey
  const { data, isPending, isFetching, isError, error, isPlaceholderData } = useLedgerTransactions(
    caseId,
    params,
    wantAll
  )
  // Counted by the server without reading the rows, so a long first load can say what it is loading.
  const count = useLedgerCount(caseId, params).data?.total
  const readingAll = wantAll && isPending
  const elapsed = useElapsedSeconds(!!caseId && readingAll)
  const loading =
    count === undefined
      ? null
      : `${count.toLocaleString("en-GB")} ${investigation ? "payment" : "row"}${count === 1 ? "" : "s"}`
  // Every row is here for this scope (not another scope's rows kept on screen while these load).
  const allRows = wantAll && !!data && !isPlaceholderData
  const firstViewOnly = firstViewMode && !allRows && !(wantAll && isError)
  // What is being read, with its count and the seconds so far (the first view's own wait, or every row's).
  const readingLine = (
    <div className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="ledger-loading">
      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
      {loading ? `Reading the ledger: ${loading}…` : "Reading the ledger..."}
      {elapsed > 0 && ` ${elapsed} s`}
    </div>
  )

  if (!caseId) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="ledger-no-case">
        Choose a case to read its ledger.
      </p>
    )
  }

  // The Transactions page's date range sits in the control panel beside the table. While the payments load, or
  // when they could not be, there is no table: the range is shown here so it can still be changed.
  const dateRange = investigation && !independentFilters && (
    <WorkspaceScope caseId={caseId} datesOnly />
  )

  if (isPending && !firstViewOnly) {
    return (
      <div className="space-y-3">
        {dateRange}
        <div
          className="flex items-center gap-2 text-sm text-muted-foreground"
          data-testid="ledger-loading"
        >
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          {loading ? `Reading the ledger: ${loading}…` : "Reading the ledger..."}
          {elapsed > 0 && ` ${elapsed} s`}
        </div>
      </div>
    )
  }

  if (isError && !firstViewOnly) {
    return (
      <div className="space-y-3">
        {dateRange}
        <div
          className="flex items-start gap-2 text-sm text-destructive"
          data-testid="ledger-error"
        >
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            Transactions could not be loaded
            {loading ? ` (${loading} in this view)` : ""}. Refresh this page to
            try again.
            {error instanceof Error ? ` ${error.message}` : ""}
          </span>
        </div>
      </div>
    )
  }

  const status = readLedgerStatus(params?.ledgerStatus ?? DEFAULT_LEDGER_STATUS)
  const rows = firstViewOnly ? [] : data!.transactions
  const countDisagrees = !firstViewOnly && data!.total !== rows.length

  const hasScopeFilter = Boolean(
    params?.accountId || params?.startDate || params?.endDate
  )
  const accountLabel = rows.find(
    (row) => row.account_id === params?.accountId
  )?.account_label
  const scope = investigation
    ? [
        params?.accountId
          ? accountLabel
            ? `Account: ${accountLabel}.`
            : "Showing the account selected above."
          : null,
        params?.startDate ? `From ${params.startDate}, inclusive.` : null,
        params?.endDate ? `To ${params.endDate}, inclusive.` : null,
      ]
        .filter(Boolean)
        .join(" ")
    : [
        params?.accountId ? `Account: ${params.accountId}.` : null,
        params?.startDate
          ? `Ordering date on or after ${params.startDate}.`
          : null,
        params?.endDate
          ? `Ordering date on or before ${params.endDate}.`
          : null,
      ]
        .filter(Boolean)
        .join(" ")

  return (
    <div className="space-y-3">
      {isFetching && !firstViewOnly && (
        <p role="status" className="text-sm text-muted-foreground">
          Updating transactions for these filters…
        </p>
      )}
      {hasScopeFilter && (
        <p
          className="text-xs text-muted-foreground"
          data-testid="ledger-filter-scope"
        >
          {scope}{" "}
          {investigation
            ? (params?.startDate || params?.endDate) &&
              "Dates use the date shown for each payment. Payments without their own transaction date are marked in the table."
            : "Date filters use the ledger ordering date, which may differ from a date printed on the statement."}
        </p>
      )}
      {rows.length > 0 && !investigation && (
        <p
          className="text-xs text-muted-foreground"
          data-testid="ledger-summary"
        >
          {`${rows.length} ${rows.length === 1 ? "row" : "rows"}, ${status.label.toLowerCase()}.`}
        </p>
      )}

      {countDisagrees && (
        <p
          className="flex items-start gap-2 text-xs text-destructive"
          data-testid="ledger-count-disagreement"
        >
          <CircleAlert className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
          <span>
            The ledger reported {data?.total} rows and sent {rows.length}. Treat
            what is below as part of the answer, not all of it.
          </span>
        </p>
      )}

      {rows.length === 0 && investigation && !firstViewOnly && (
        <p className="rounded border p-3" role="status">
          {hasScopeFilter
            ? "No payments match these filters"
            : "No imported payments yet"}
          {hasScopeFilter
            ? ". Change the filters below to see other payments."
            : ". Add statements to import their payments."}
        </p>
      )}
      {rows.length === 0 && !investigation && !firstViewOnly ? (
        <EmptyState
          icon={ScrollText}
          title={
            investigation
              ? hasScopeFilter
                ? "No payments match these filters"
                : "No imported payments yet"
              : hasScopeFilter
                ? `No ${status.label.toLowerCase()} rows match these filters`
                : `No ${status.label.toLowerCase()} rows in the ledger`
          }
          description={
            investigation
              ? hasScopeFilter
                ? "Clear or change the account and date filters to see other payments. You can check statement imports in Statements."
                : "Open Statements to upload a PDF, check its transactions and confirm the import. Confirmed payments will appear here."
              : `No rows were returned for status "${status.label.toLowerCase()}"` +
                (hasScopeFilter
                  ? " within the account/date filters."
                  : " in this case's ledger.") +
                " Rows with other statuses, including quarantined, superseded or rejected readings, are not counted here unless that status is selected." +
                " This does not establish that no transactions occurred or that the records are complete. Check statement coverage and unfinished processing attempts."
          }
        />
      ) : (
        <LedgerRowBrowser
          independentFilters={independentFilters}
          key={caseId}
          transactions={rows}
          exportContext={
            caseId &&
            (params?.ledgerStatus ?? DEFAULT_LEDGER_STATUS) === "admitted"
              ? { caseId, params: params ?? {} }
              : undefined
          }
          onAdjudicate={onAdjudicate}
          onCorrect={onCorrect}
          onSource={onSource}
          onNote={onNote}
          splitAmounts={splitAmounts}
          investigation={investigation}
          firstView={
            firstViewOnly
              ? {
                  params,
                  readingAll,
                  loading: (
                    <>
                      {dateRange}
                      {readingLine}
                    </>
                  ),
                  status: readingLine,
                  onNeedAll: () => setWanted(scopeKey),
                }
              : undefined
          }
        />
      )}
    </div>
  )
}
