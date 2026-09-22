import { AddToTimelineDialog } from "@/features/timeline/components/AddToTimelineDialog"
import { matchesAccountSelection } from "../lib/account-selection"
import { compareDisplayedAmounts } from "../lib/transaction-search"
import { transactionSearch } from "../lib/transaction-search"
import { TransactionAnalysisControls } from "./TransactionAnalysisPanels"
import { useInvestigationScope } from "../stores/investigation-scope"
import { retainPaymentTableView } from "../lib/payment-table-draft"
import { PaymentCategoryFilter } from "./PaymentCategoryFilter"
import { TransactionNotesCsv } from "./TransactionNotesCsv"
import { downloadCsv, transactionCsv } from "../lib/transaction-csv"
import {
  AnalysisFilterChips,
  TransactionAnalysisPanels,
} from "./TransactionAnalysisPanels"
import { TransactionExplorerTable } from "./TransactionExplorerTable"
import {
  analysisTableView,
  filterAnalysis,
  sortAnalysisRows,
} from "../lib/transaction-analysis"
import { PaymentEditsEditor } from "./PaymentEditsEditor"
import { PaymentCategoryManager } from "./PaymentCategoryManager"
import { TransactionAccountFilters } from "./TransactionAccountFilters"
import {
  usePaymentCategory,
  categoryName,
} from "../hooks/use-payment-categories"
import { useFinancialFindingIndex } from "../hooks/use-financial-finding-index"
import { ExportSelectedPayments } from "./ExportSelectedPayments"
import { PaymentComparison } from "./PaymentComparison"
import { InvestigatorFindingEditor } from "./InvestigatorFindingEditor"
import { useFinancialAccess } from "../hooks/use-financial-access"
import { SelectedPaymentsReview } from "./SelectedPaymentsReview"
import {
  emptyPaymentTableView as emptyView,
  paymentTableDraftName,
} from "../lib/payment-table-draft"
import { PaymentTotals } from "./InvestigationTransactionTable"
import { SavePaymentSelection } from "./SavePaymentSelection"
import { useFinancialDraft } from "../stores/financial-drafts"
import { correctionMinor } from "../lib/correction-contract"
import { LedgerExportButton } from "./LedgerExportButton"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { useState, type ComponentProps } from "react"
import { Button } from "@/components/ui/button"
import { LedgerTable } from "./LedgerTable"
import type { LedgerTransaction } from "../api"
function exactAmount(row: LedgerTransaction) {
  const value = row.amount_minor
  if (typeof value === "number" && !Number.isSafeInteger(value)) return null
  const text = String(value)
  return /^(0|[1-9][0-9]{0,18})$/.test(text) ? BigInt(text) : null
}
export function LedgerRowBrowser({
  transactions,
  exportContext,
  investigation = false,
  ...actions
}: ComponentProps<typeof LedgerTable> & {
  investigation?: boolean
  exportContext?: {
    caseId: string
    params: LedgerQueryParams
    profile?: { id: string; group: string }
  }
}) {
  const [accountScope, applyAccountScope] = useInvestigationScope(
    exportContext?.caseId
  )
  const { canEdit } = useFinancialAccess()
  const [category, setCategory] = usePaymentCategory(
    exportContext?.caseId ?? "none"
  )
  const [notesCsv, setNotesCsv] = useState(false)
  const [manageCategories, setManageCategories] = useState(false)
  const [editNames, setEditNames] = useState(false)
  const [labelIds, setLabelIds] = useState<string[] | null>(null)
  const findings = useFinancialFindingIndex(
    investigation ? exportContext?.caseId : undefined
  )
  const [timeline, setTimeline] = useState(false)
  const [compare, setCompare] = useState(false)
  const [finding, setFinding] = useState<"question" | "observation" | null>(
    null
  )
  const [reviewSelection, setReviewSelection] = useState(false)
  const [localView, setLocalView] = useState(emptyView)
  const [savedView, setSavedView] = useFinancialDraft(
    exportContext?.caseId ?? "none",
    paymentTableDraftName(exportContext?.params, investigation) +
      (exportContext?.profile
        ? `:profile:${JSON.stringify(exportContext.profile)}`
        : ""),
    exportContext?.profile ? { ...emptyView, chartsOpen: true } : emptyView
  )
  const view = { ...emptyView, ...(exportContext ? savedView : localView) }
  const setView = exportContext ? setSavedView : setLocalView
  const {
    search,
    searchMode = "text",
    currency,
    minimum,
    maximum,
    direction,
    proof,
    sort,
    page,
    pageSize,
    sourceDocumentId = "",
    sourceFilename = "",
    importBatchId = "",
    importBatchRevision = "",
    importSourceIds = [],
    importStatementCount = 0,
  } = view
  const changeView = (changes: Partial<typeof emptyView>) =>
    setView((previous) => ({ ...previous, page: 0, ...changes }))
  const [selection, setSelection] = useFinancialDraft<string[]>(
    exportContext?.caseId ?? "none",
    "selected-payments",
    []
  )
  const selectedIds = new Set(selection)
  const selectedHere = transactions.filter((row) => selectedIds.has(row.key))
  const toggle = (row: LedgerTransaction, checked: boolean) =>
    setSelection((previous) =>
      checked
        ? [...new Set([...previous, row.key])]
        : previous.filter((id) => id !== row.key)
    )
  const searchResult = transactionSearch(search, searchMode)
  const minMinor = minimum.trim() ? correctionMinor(minimum, currency) : ""
  const maxMinor = maximum.trim() ? correctionMinor(maximum, currency) : ""
  const invalidRange =
    minMinor === null ||
    maxMinor === null ||
    (!!minMinor && !!maxMinor && BigInt(minMinor) > BigInt(maxMinor))
  const batchSources = new Set(importSourceIds)
  const baseRows = transactions.filter(
    (row) =>
      !invalidRange &&
      matchesAccountSelection(row, accountScope) &&
      (!category || categoryName(row) === category) &&
      (!sourceDocumentId || row.source_document_id === sourceDocumentId) &&
      (!importBatchId || batchSources.has(row.source_document_id)) &&
      (!minMinor ||
        (exactAmount(row) !== null && exactAmount(row)! >= BigInt(minMinor))) &&
      (!maxMinor ||
        (exactAmount(row) !== null && exactAmount(row)! <= BigInt(maxMinor))) &&
      (!currency || row.currency === currency) &&
      (!direction || row.direction === direction) &&
      (!proof || row.proof_class === proof) &&
      searchResult.matches(row)
  )
  const rows = investigation ? filterAnalysis(baseRows, view) : baseRows
  sortAnalysisRows(rows, sort)
  const mixedCurrencies = new Set(rows.map((row) => row.currency)).size > 1
  if (sort === "newest")
    rows.sort((a, b) => b.ordering_date.localeCompare(a.ordering_date))
  if (sort === "oldest")
    rows.sort((a, b) => a.ordering_date.localeCompare(b.ordering_date))
  if (sort.startsWith("amount"))
    rows.sort((a, b) => {
      const order = compareDisplayedAmounts(a, b)
      return sort === "amount-desc" ? -order : order
    })
  const index = Math.min(
    page,
    Math.max(0, Math.ceil(rows.length / pageSize) - 1)
  )
  const transactionToolbar = (
    <div
      className="sticky top-0 z-20 max-h-[55vh] overflow-y-auto rounded border bg-background p-3 shadow-sm"
      role="region"
      aria-label="Transaction tools and filters"
    >
      <div className="flex flex-wrap items-end gap-3">
        {investigation && exportContext && canEdit && (
          <Button variant="outline" onClick={() => setManageCategories(true)}>
            Manage categories
          </Button>
        )}
        <label>
          Search payments
          <input
            aria-label="Search payments"
            className="block w-full min-w-52 rounded border bg-background p-2"
            maxLength={256}
            aria-invalid={!!searchResult.error}
            value={search}
            onChange={(e) => {
              changeView({ search: e.target.value })
            }}
            placeholder={
              searchMode === "boolean"
                ? '(from:"Acme" OR category:Transfers) AND NOT refund'
                : "Description, name, reference or amount"
            }
          />
        </label>
        <label className="text-sm">
          Search mode
          <select
            aria-label="Transaction search mode"
            className="block rounded border bg-background p-2"
            value={searchMode}
            onChange={(event) => changeView({ searchMode: event.target.value })}
          >
            <option value="text">Text filter</option>
            <option value="boolean">Boolean search</option>
          </select>
        </label>
        {search && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => changeView({ search: "" })}
          >
            Clear search
          </Button>
        )}
        {exportContext && (
          <PaymentCategoryFilter caseId={exportContext.caseId} />
        )}
        {investigation && (
          <>
            <Button
              variant="outline"
              size="sm"
              disabled={!rows.length}
              onClick={() =>
                downloadCsv(
                  transactionCsv(rows),
                  "loupe-filtered-transactions.csv"
                )
              }
            >
              Download CSV ({rows.length.toLocaleString()})
            </Button>
            {canEdit && exportContext && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setNotesCsv(true)}
              >
                Notes CSV
              </Button>
            )}
          </>
        )}
        <details className="rounded border p-2 text-sm">
          <summary className="cursor-pointer">
            Filters
            {[currency, category, minimum, maximum, direction, proof].filter(
              Boolean
            ).length > 0 &&
              ` (${[currency, category, minimum, maximum, direction, proof].filter(Boolean).length})`}
          </summary>
          <div className="flex flex-wrap gap-3 pt-3">
            <label>
              Currency
              <select
                aria-label="Currency"
                className="block rounded border bg-background p-2"
                value={currency}
                onChange={(e) => {
                  changeView({
                    currency: e.target.value,
                    minimum: "",
                    maximum: "",
                  })
                }}
              >
                <option value="">All currencies</option>
                {[...new Set(transactions.map((r) => r.currency))]
                  .sort()
                  .map((c) => (
                    <option key={c}>{c}</option>
                  ))}
              </select>
            </label>
            <label>
              Sort payments
              <select
                aria-label="Sort payments"
                className="block rounded border bg-background p-2"
                value={sort}
                onChange={(e) => {
                  changeView({ sort: e.target.value })
                }}
              >
                <option value="ledger">Recorded date order</option>
                <option value="oldest">Oldest first</option>
                <option value="newest">Newest first</option>
                <option value="description-asc">Description A–Z</option>
                <option value="description-desc">Description Z–A</option>
                <option value="from-asc">Sender A–Z</option>
                <option value="from-desc">Sender Z–A</option>
                <option value="to-asc">Recipient A–Z</option>
                <option value="to-desc">Recipient Z–A</option>
                <option value="category-asc">Category A–Z</option>
                <option value="category-desc">Category Z–A</option>
                <option value="amount-desc">Largest amount first</option>
                <option value="amount-asc">Smallest amount first</option>
              </select>
            </label>
            <Button
              variant="outline"
              onClick={() => {
                setView(emptyView)
                setCategory("")
              }}
            >
              Clear payment filters
            </Button>{" "}
            <label>
              Minimum amount {currency}
              <input
                aria-label="Table minimum amount"
                className="block w-40 rounded border bg-background p-2"
                inputMode="decimal"
                maxLength={32}
                disabled={!currency}
                value={minimum}
                onChange={(e) => {
                  changeView({ minimum: e.target.value })
                }}
              />
            </label>
            <label>
              Maximum amount {currency}
              <input
                aria-label="Table maximum amount"
                className="block w-40 rounded border bg-background p-2"
                inputMode="decimal"
                maxLength={32}
                disabled={!currency}
                value={maximum}
                onChange={(e) => {
                  changeView({ maximum: e.target.value })
                }}
              />
            </label>
            <label>
              Money in or out
              <select
                aria-label="Money in or out"
                className="block rounded border bg-background p-2"
                value={direction}
                onChange={(e) => {
                  changeView({ direction: e.target.value })
                }}
              >
                <option value="">Both directions</option>
                <option value="credit">Incoming</option>
                <option value="debit">Outgoing</option>
              </select>
            </label>
            <details>
              <summary className="text-sm cursor-pointer">
                Technical filter
              </summary>
              <label>
                Evidence classification
                <select
                  aria-label="Table proof class"
                  className="block rounded border bg-background p-2"
                  value={proof}
                  onChange={(e) => {
                    changeView({ proof: e.target.value })
                  }}
                >
                  <option value="">All proof classes</option>
                  {[...new Set(transactions.map((r) => r.proof_class))]
                    .sort()
                    .map((p) => (
                      <option key={p}>{p}</option>
                    ))}
                </select>
              </label>
            </details>
            <p className="basis-full text-xs text-muted-foreground">
              Choose a currency to filter by amount.
            </p>
          </div>
        </details>
      </div>
      {searchMode === "boolean" && (
        <p className="mt-2 text-xs text-muted-foreground">
          AND, OR, NOT, quoted phrases and parentheses. Adjacent terms mean AND.
          Fields: from:, to:, category:, description:, reference:, date:,
          currency:, account:, amount:.
        </p>
      )}
      {searchResult.error && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {searchResult.error}
        </p>
      )}
      {investigation && (
        <TransactionAnalysisControls
          filters={view}
          panels={view}
          onChange={changeView}
        />
      )}
    </div>
  )
  return (
    <section aria-label="Browse ledger rows" className="space-y-3">
      {investigation && exportContext && (
        <TransactionAccountFilters
          caseId={exportContext.caseId}
          selection={accountScope}
          onChange={(selection) => {
            const next = { ...accountScope, ...selection }
            retainPaymentTableView(exportContext.caseId, accountScope, next)
            applyAccountScope(next)
          }}
        />
      )}
      {importBatchId && (
        <div
          className="flex flex-wrap items-center justify-between gap-3 rounded border bg-card p-3"
          role="region"
          aria-label="Imported batch transactions"
        >
          <p>
            Payments from{" "}
            <strong>{importStatementCount} imported statements</strong> in this
            batch. Account, date and payment filters also apply.
          </p>
          <div className="flex gap-3 items-center">
            {exportContext && (
              <a
                className="underline"
                href={`/cases/${exportContext.caseId}/financial?view=statements&batch=${importBatchId}`}
              >
                Open import batch
              </a>
            )}
            <Button
              variant="outline"
              onClick={() =>
                changeView({
                  importBatchId: "",
                  importBatchRevision: "",
                  importSourceIds: [],
                  importStatementCount: 0,
                })
              }
            >
              Clear batch filter
            </Button>
          </div>
        </div>
      )}
      {sourceDocumentId && (
        <div
          className="flex flex-wrap items-center justify-between gap-3 rounded border bg-card p-3"
          role="region"
          aria-label="Selected statement transactions"
        >
          <p>
            Statement: <strong>{sourceFilename || "Selected statement"}</strong>
          </p>
          <Button
            variant="outline"
            onClick={() =>
              changeView({ sourceDocumentId: "", sourceFilename: "" })
            }
          >
            Clear statement filter
          </Button>
        </div>
      )}
      {notesCsv && exportContext && (
        <TransactionNotesCsv
          caseId={exportContext.caseId}
          rows={transactions}
          onClose={() => setNotesCsv(false)}
        />
      )}
      {!investigation && transactionToolbar}
      <div
        className="flex flex-wrap gap-2 text-xs"
        aria-label="Applied payment filters"
      >
        {currency && (
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              changeView({ currency: "", minimum: "", maximum: "" })
            }
          >
            {currency} ×
          </Button>
        )}
        {category && (
          <Button size="sm" variant="outline" onClick={() => setCategory("")}>
            {category} ×
          </Button>
        )}
        {direction && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => changeView({ direction: "" })}
          >
            {direction === "credit" ? "Incoming" : "Outgoing"} ×
          </Button>
        )}
        {(minimum || maximum) && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => changeView({ minimum: "", maximum: "" })}
          >
            Amount: {minimum || "any"} – {maximum || "any"} {currency} ×
          </Button>
        )}
        {proof && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => changeView({ proof: "" })}
          >
            Classification: {proof} ×
          </Button>
        )}
      </div>
      {invalidRange && (
        <p role="alert">
          Enter valid amounts for {currency}, with the minimum no greater than
          the maximum. The table export is unavailable until the range is valid.
        </p>
      )}
      {!investigation && (
        <p className="text-sm text-muted-foreground">
          {rows.length} payments match your filters.
        </p>
      )}
      {investigation && exportContext && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <strong>
              {rows.length.toLocaleString()} of{" "}
              {transactions.length.toLocaleString()} imported transactions
            </strong>
            <span className="text-xs text-muted-foreground">
              Totals and analysis include every matching transaction, across all
              pages.
            </span>
          </div>
          <AnalysisFilterChips filters={view} onChange={changeView} />
          <PaymentTotals rows={rows} label="Payments matching your filters" />
          {transactionToolbar}
          {sort.startsWith("amount") && mixedCurrencies && (
            <p className="text-xs text-muted-foreground">
              Sorted by amount size across currencies. Money in or out does not
              change this order; currencies are not converted.
            </p>
          )}
          <TransactionAnalysisPanels
            hideControls
            rows={baseRows}
            filters={view}
            panels={view}
            onChange={changeView}
          />
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span>
                {selection.length
                  ? `${selection.length} payments selected`
                  : `${rows.length} matching payments`}
              </span>
              <Button
                variant="outline"
                disabled={
                  !rows.length || rows.every((row) => selectedIds.has(row.key))
                }
                onClick={() =>
                  setSelection((previous) => [
                    ...new Set([...previous, ...rows.map((row) => row.key)]),
                  ])
                }
              >
                Select all {rows.length} matching payments
              </Button>
              {selection.length > 0 && (
                <Button
                  variant="ghost"
                  disabled={!selection.length}
                  onClick={() => setSelection([])}
                >
                  Clear selection
                </Button>
              )}
            </div>
            {selection.length > 0 && (
              <>
                <div className="flex flex-wrap items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 p-3">
                  <Button variant="outline" onClick={() => setCompare(true)}>
                    Compare payments
                  </Button>
                  {canEdit && (
                    <>
                      <Button
                        onClick={() => {
                          setEditNames(true)
                          setLabelIds(selection)
                        }}
                      >
                        Edit selected transactions
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => {
                          setEditNames(false)
                          setLabelIds(selection)
                        }}
                      >
                        Categorize selected
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => setTimeline(true)}
                      >
                        Add to Timeline
                      </Button>
                      <Button onClick={() => setFinding("observation")}>
                        Create finding
                      </Button>
                    </>
                  )}
                  {canEdit && (
                    <Button
                      variant="outline"
                      onClick={() => setFinding("question")}
                    >
                      Create observation
                    </Button>
                  )}
                  <ExportSelectedPayments
                    caseId={exportContext.caseId}
                    ids={selection}
                  />
                </div>
                {timeline && (
                  <AddToTimelineDialog
                    caseId={exportContext.caseId}
                    ids={selection}
                    onClose={() => setTimeline(false)}
                  />
                )}
                {compare && (
                  <PaymentComparison
                    caseId={exportContext.caseId}
                    ids={selection}
                    onClose={() => setCompare(false)}
                  />
                )}
                {finding && (
                  <InvestigatorFindingEditor
                    caseId={exportContext.caseId}
                    ids={selection}
                    initial={{ kind: finding }}
                    onClose={() => setFinding(null)}
                  />
                )}
                <details className="text-sm">
                  <summary className="cursor-pointer">
                    Selected amounts and saved selections
                  </summary>
                  <div className="space-y-3 pt-2">
                    <PaymentTotals
                      rows={selectedHere}
                      label="Selected payments in this account/date range"
                    />
                    <SavePaymentSelection
                      onReviewSelection={() => setReviewSelection(true)}
                      caseId={exportContext.caseId}
                      ids={selection}
                    />
                  </div>
                </details>
                {selection.length >
                  rows.filter((row) => selectedIds.has(row.key)).length && (
                  <p className="text-sm rounded border p-2">
                    {selection.length -
                      rows.filter((row) => selectedIds.has(row.key))
                        .length}{" "}
                    selected payments are hidden by the current filters. Compare
                    or review the selection to see every attached payment.
                  </p>
                )}
                {selection.length > selectedHere.length && (
                  <p>
                    {selection.length - selectedHere.length} selected payments
                    are outside this account/date range. They will also be
                    included when you save the selection.
                  </p>
                )}
                <Button
                  variant="outline"
                  onClick={() => setReviewSelection(true)}
                >
                  Review selected payments
                </Button>
                {reviewSelection && (
                  <SelectedPaymentsReview
                    key={exportContext.caseId}
                    caseId={exportContext.caseId}
                    ids={selection}
                    onRemove={(id) => {
                      setSelection((previous) =>
                        previous.filter((value) => value !== id)
                      )
                      if (selection.length === 1) setReviewSelection(false)
                    }}
                    onClose={() => setReviewSelection(false)}
                  />
                )}
              </>
            )}
          </div>
        </>
      )}
      {labelIds && exportContext && (
        <PaymentEditsEditor
          key={labelIds.join(",")}
          caseId={exportContext.caseId}
          ids={labelIds}
          initialField={editNames ? undefined : "category"}
          onSaved={(replacements) => {
            const mapping = new Map(
              replacements.map((row) => [row.previous_id, row.id])
            )
            setSelection((previous) =>
              previous.map((id) => mapping.get(id) ?? id)
            )
          }}
          onClose={() => setLabelIds(null)}
        />
      )}
      {manageCategories && exportContext && (
        <PaymentCategoryManager
          caseId={exportContext.caseId}
          onClose={() => setManageCategories(false)}
        />
      )}
      {investigation && findings.isError && (
        <p role="alert" className="text-sm">
          Saved finding links could not be loaded.{" "}
          <button className="underline" onClick={() => void findings.refetch()}>
            Reload finding links
          </button>
        </p>
      )}
      {!rows.length ? (
        <p>
          No payments match these filters. Clear the filters or choose another
          account/date range.
        </p>
      ) : investigation && exportContext ? (
        <TransactionExplorerTable
          findings={findings.data}
          rows={rows.slice(index * pageSize, (index + 1) * pageSize)}
          selected={selection}
          expanded={view.expandedRows}
          sort={sort}
          onSort={(sort) => changeView({ sort })}
          onExpand={(expandedRows) =>
            setView((previous) => ({ ...previous, expandedRows }))
          }
          onToggle={toggle}
          onOpen={actions.onSource}
          onNote={actions.onNote}
          onEdit={
            canEdit
              ? (row) => {
                  setEditNames(true)
                  setLabelIds([row.key])
                }
              : undefined
          }
          onCategory={
            canEdit
              ? (row) => {
                  setEditNames(false)
                  setLabelIds([row.key])
                }
              : undefined
          }
          onParty={(side, key) => {
            const field = side === "from" ? "fromNames" : "toNames"
            changeView({
              [field]: view[field].includes(key)
                ? view[field].filter((n) => n !== key)
                : [...view[field], key],
            })
          }}
        />
      ) : (
        <LedgerTable
          transactions={rows.slice(index * pageSize, (index + 1) * pageSize)}
          {...actions}
        />
      )}
      {exportContext && !invalidRange && (
        <details className="rounded border p-3">
          <summary className="cursor-pointer font-medium">
            Download these transactions
          </summary>
          <LedgerExportButton
            caseId={exportContext.caseId}
            params={{ ...exportContext.params, ...accountScope }}
            tableView={{
              ...analysisTableView(view),
              ...(exportContext.profile
                ? {
                    profile_id: exportContext.profile.id,
                    profile_group: exportContext.profile.group,
                  }
                : {}),
              search,
              search_mode: searchMode as "text" | "boolean",
              ...(category ? { category } : {}),
              ...(sourceDocumentId
                ? { source_document_id: sourceDocumentId }
                : {}),
              ...(importBatchId
                ? {
                    import_batch_id: importBatchId,
                    import_batch_revision: importBatchRevision,
                  }
                : {}),
              currency,
              direction,
              proof,
              minimum_minor: minMinor ?? "",
              maximum_minor: maxMinor ?? "",
              sort,
            }}
          />
        </details>
      )}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label>
          Rows per page{" "}
          <select
            aria-label="Rows per page"
            className="rounded border bg-background p-1"
            value={pageSize}
            onChange={(e) => changeView({ pageSize: Number(e.target.value) })}
          >
            {[25, 50, 100, 250].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        {rows.length > pageSize && (
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              disabled={!index}
              onClick={() => changeView({ page: index - 1 })}
            >
              Previous ledger rows
            </Button>
            <span>
              {index * pageSize + 1}–
              {Math.min((index + 1) * pageSize, rows.length)} of {rows.length}{" "}
              matching rows
            </span>
            <Button
              variant="outline"
              disabled={(index + 1) * pageSize >= rows.length}
              onClick={() => changeView({ page: index + 1 })}
            >
              Next ledger rows
            </Button>
          </div>
        )}
      </div>
    </section>
  )
}
