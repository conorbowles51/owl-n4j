import { PaymentLabelsEditor } from "./PaymentLabelsEditor"
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
import {
  InvestigationTransactionTable,
  PaymentTotals,
} from "./InvestigationTransactionTable"
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
  exportContext?: { caseId: string; params: LedgerQueryParams }
}) {
  const { canEdit } = useFinancialAccess()
  const [category, setCategory] = usePaymentCategory(
    exportContext?.caseId ?? "none"
  )
  const [labelIds, setLabelIds] = useState<string[] | null>(null)
  const findings = useFinancialFindingIndex(
    investigation ? exportContext?.caseId : undefined
  )
  const [compare, setCompare] = useState(false)
  const [finding, setFinding] = useState<"question" | "observation" | null>(
    null
  )
  const [reviewSelection, setReviewSelection] = useState(false)
  const [localView, setLocalView] = useState(emptyView)
  const [savedView, setSavedView] = useFinancialDraft(
    exportContext?.caseId ?? "none",
    paymentTableDraftName(exportContext?.params, investigation),
    emptyView
  )
  const view = exportContext ? savedView : localView
  const setView = exportContext ? setSavedView : setLocalView
  const {
    search,
    currency,
    minimum,
    maximum,
    direction,
    proof,
    sort,
    page,
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
  const query = search.trim().toLowerCase()
  const minMinor = minimum.trim() ? correctionMinor(minimum, currency) : ""
  const maxMinor = maximum.trim() ? correctionMinor(maximum, currency) : ""
  const invalidRange =
    minMinor === null ||
    maxMinor === null ||
    (!!minMinor && !!maxMinor && BigInt(minMinor) > BigInt(maxMinor))
  const batchSources = new Set(importSourceIds)
  const rows = transactions.filter(
    (row) =>
      !invalidRange &&
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
      (!query ||
        [
          row.ordering_date,
          row.description,
          row.from_name,
          row.to_name,
          row.category,
          row.counterparty_raw,
          row.bank_reference,
          row.ref_id,
          row.key,
          row.account_id,
          row.source_document_id,
        ].some(
          (value) =>
            typeof value === "string" && value.toLowerCase().includes(query)
        ))
  )
  const amountAllowed = new Set(rows.map((row) => row.currency)).size <= 1
  if (sort === "newest")
    rows.sort((a, b) => b.ordering_date.localeCompare(a.ordering_date))
  if (sort === "oldest")
    rows.sort((a, b) => a.ordering_date.localeCompare(b.ordering_date))
  if (sort.startsWith("amount") && amountAllowed)
    rows.sort((a, b) => {
      const left = exactAmount(a),
        right = exactAmount(b)
      if (left === null) return right === null ? 0 : 1
      if (right === null) return -1
      const order = left < right ? -1 : left > right ? 1 : 0
      return sort === "amount-desc" ? -order : order
    })
  const index = Math.min(page, Math.max(0, Math.ceil(rows.length / 50) - 1))
  return (
    <section aria-label="Browse ledger rows" className="space-y-3">
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
      <div className="flex flex-wrap items-end gap-3">
        <label>
          Search payments
          <input
            aria-label="Search payments"
            className="block w-full min-w-52 rounded border bg-background p-2"
            maxLength={256}
            value={search}
            onChange={(e) => {
              changeView({ search: e.target.value })
            }}
            placeholder="Description, name or reference"
          />
        </label>
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
                    sort: sort.startsWith("amount") ? "ledger" : sort,
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
                <option value="amount-desc" disabled={!amountAllowed}>
                  Largest amount first (one currency)
                </option>
                <option value="amount-asc" disabled={!amountAllowed}>
                  Smallest amount first (one currency)
                </option>
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
            </Button>
            <label>
              Category
              <select
                aria-label="Category filter"
                className="block rounded border bg-background p-2"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                <option value="">All categories</option>
                {[...new Set(transactions.map(categoryName))]
                  .sort()
                  .map((value) => (
                    <option key={value}>{value}</option>
                  ))}
              </select>
            </label>{" "}
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
          <PaymentTotals rows={rows} label="Payments matching your filters" />
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
                        variant="outline"
                        onClick={() => setLabelIds(selection)}
                      >
                        Categorize selected
                      </Button>
                      <Button onClick={() => setFinding("observation")}>
                        Create finding
                      </Button>
                    </>
                  )}
                  <details>
                    <summary className="cursor-pointer rounded border px-3 py-2 text-sm">
                      More actions
                    </summary>
                    <div className="flex flex-wrap gap-2 p-2">
                      {canEdit && (
                        <Button
                          variant="outline"
                          onClick={() => setFinding("question")}
                        >
                          Mark for follow-up
                        </Button>
                      )}
                      <ExportSelectedPayments
                        caseId={exportContext.caseId}
                        ids={selection}
                      />
                    </div>
                  </details>
                </div>
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
        <PaymentLabelsEditor
          key={labelIds.join(",")}
          caseId={exportContext.caseId}
          ids={labelIds}
          onClose={() => setLabelIds(null)}
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
        <InvestigationTransactionTable
          compact
          showAccount={new Set(rows.map((row) => row.account_id)).size > 1}
          findings={findings.data}
          rows={rows.slice(index * 50, index * 50 + 50)}
          selected={selection}
          onToggle={toggle}
          onOpen={actions.onSource}
          onNote={actions.onNote}
          onCategorize={canEdit ? (row) => setLabelIds([row.key]) : undefined}
        />
      ) : (
        <LedgerTable
          transactions={rows.slice(index * 50, index * 50 + 50)}
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
            params={exportContext.params}
            tableView={{
              search,
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
              sort:
                sort.startsWith("amount") && !amountAllowed ? "ledger" : sort,
            }}
          />
        </details>
      )}
      {rows.length > 50 && (
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            disabled={!index}
            onClick={() => changeView({ page: index - 1 })}
          >
            Previous ledger rows
          </Button>
          <span>
            {index * 50 + 1}–{Math.min((index + 1) * 50, rows.length)} of{" "}
            {rows.length} matching rows
          </span>
          <Button
            variant="outline"
            disabled={(index + 1) * 50 >= rows.length}
            onClick={() => changeView({ page: index + 1 })}
          >
            Next ledger rows
          </Button>
        </div>
      )}
    </section>
  )
}
