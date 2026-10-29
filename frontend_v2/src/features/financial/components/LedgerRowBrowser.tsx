import { AddToTimelineDialog } from "@/features/timeline/components/AddToTimelineDialog"
import { useMoneyTrails } from "../hooks/use-money-trails"
import { internalActivity, activityAmount } from "../lib/money-trails"
import { correctionMoney } from "../lib/correction-contract"
import { matchesAccountSelection } from "../lib/account-selection"
import { compareDisplayedAmounts } from "../lib/transaction-search"
import { transactionSearch } from "../lib/transaction-search"
import { TransactionAnalysisControls } from "./TransactionAnalysisPanels"
import { useInvestigationScope } from "../stores/investigation-scope"
import { retainPaymentTableView } from "../lib/payment-table-draft"
import { PaymentCategoryFilter } from "./PaymentCategoryFilter"
import { useCategoryColors } from "../hooks/use-payment-category-library"
import { TransactionNotesCsv } from "./TransactionNotesCsv"
import { downloadCsv, transactionCsv } from "../lib/transaction-csv"
import {
  AnalysisFilterChips,
  TransactionAnalysisPanels,
} from "./TransactionAnalysisPanels"
import { TableColumnPicker, TransactionExplorerTable } from "./TransactionExplorerTable"
import { readProofClass } from "../lib/ledger-format"
import { readTableColumns, storeTableColumns } from "../lib/table-columns"
import { PaymentCardList } from "./PaymentCardList"
import { TransactionsOverview } from "./TransactionsOverview"
import { Disclosure } from "./Disclosure"
import {
  analysisTableView,
  filterAnalysis,
  sortAnalysisRows,
} from "../lib/transaction-analysis"
import { PaymentEditsEditor } from "./PaymentEditsEditor"
import { CategorisePaymentDialog } from "./CategorisePaymentDialog"
import { PaymentCategoryManager } from "./PaymentCategoryManager"
import { TransactionAccountFilters } from "./TransactionAccountFilters"
import { useLedgerAccountDirectory } from "../hooks/use-ledger-account-directory"
import {
  knownAccountGroup,
  knownPaymentAccounts,
} from "../lib/known-payment-accounts"
import {
  usePaymentCategory,
  matchesCategories,
  useStatementNames,
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
import { useRowJudgementLookup } from "../hooks/use-judgement-rows"
import { useJudgementRowMap } from "../hooks/use-judgements"
import {
  STATUS_LABELS,
  STRENGTH_LABELS,
  ORIGIN_LABELS,
  type Judgement,
} from "../lib/judgements"
import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { useCallback, useRef, useState, type ComponentProps } from "react"
import { Button } from "@/components/ui/button"
import { LedgerTable } from "./LedgerTable"
import { PaymentNamingPanel } from "./PaymentNamingPanel"
import { needsConfirm, needsName } from "../lib/payment-naming"
import type { LedgerTransaction } from "../api"
const TABLE_VIEW_KEY = "financial-transactions-table-view"
function readTableView() {
  try {
    return localStorage.getItem(TABLE_VIEW_KEY) === "1"
  } catch {
    return false
  }
}
function storeTableView(on: boolean) {
  try {
    localStorage.setItem(TABLE_VIEW_KEY, on ? "1" : "0")
  } catch {
    // The choice still applies for this visit.
  }
}

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
  independentFilters = false,
  ...actions
}: ComponentProps<typeof LedgerTable> & {
  investigation?: boolean
  independentFilters?: boolean
  exportContext?: {
    caseId: string
    params: LedgerQueryParams
    profile?: {
      id: string
      group: string
      scope?: "owned_accounts" | "counterparty_payments"
    }
  }
}) {
  const [sharedAccountScope, applySharedAccountScope] = useInvestigationScope(
    exportContext?.caseId
  )
  const [localAccountScope, applyLocalAccountScope] = useState<
    typeof sharedAccountScope
  >({})
  const accountScope = independentFilters
    ? localAccountScope
    : sharedAccountScope
  const applyAccountScope = independentFilters
    ? applyLocalAccountScope
    : applySharedAccountScope
  const { canEdit } = useFinancialAccess()
  const accountDirectory = useLedgerAccountDirectory(
    investigation && !exportContext?.profile ? exportContext?.caseId : undefined
  )
  const trails = useMoneyTrails(
    investigation ? exportContext?.caseId : undefined
  )
  const [sharedCategories, setSharedCategories] = usePaymentCategory(
    exportContext?.caseId ?? "none"
  )
  const [localCategories, setLocalCategories] = useState<string[]>([])
  const categoryColors = useCategoryColors(exportContext?.caseId ?? "none")
  const categories = independentFilters ? localCategories : sharedCategories
  const setCategories = independentFilters
    ? setLocalCategories
    : setSharedCategories
  const [notesCsv, setNotesCsv] = useState(false)
  const [manageCategories, setManageCategories] = useState(false)
  const [editNames, setEditNames] = useState(false)
  const [naming, setNaming] = useState<string | null>(null)
  // The tools bar sticks over the table; the naming panel sticks just below it so its header stays visible.
  const [toolbarHeight, setToolbarHeight] = useState(0)
  const toolbarWatch = useRef<ResizeObserver | null>(null)
  const toolbarRef = useCallback((node: HTMLDivElement | null) => {
    toolbarWatch.current?.disconnect()
    toolbarWatch.current = null
    if (!node) return
    setToolbarHeight(node.offsetHeight)
    if (typeof ResizeObserver === "undefined") return
    toolbarWatch.current = new ResizeObserver(() => setToolbarHeight(node.offsetHeight))
    toolbarWatch.current.observe(node)
  }, [])
  // "confirm": the panel works names Claude read that no person has confirmed.
  const [namingMode, setNamingMode] = useState<"name" | "confirm">("name")
  const [labelIds, setLabelIds] = useState<string[] | null>(null)
  // The quick Categorise dialog; "Edit other fields…" swaps in the full editor.
  const [fullEditor, setFullEditor] = useState(false)
  // Walking the current list one payment at a time from a row's category chip.
  const [walk, setWalk] = useState<{ queue: string[]; done: number } | null>(null)
  const findings = useFinancialFindingIndex(
    investigation ? exportContext?.caseId : undefined
  )
  const [timeline, setTimeline] = useState(false)
  const [tableView, setTableView] = useState(readTableView)
  const [tableColumns, setTableColumns] = useState(readTableColumns)
  const tableStatementNames =
    useStatementNames(tableView && tableColumns.includes("statement") && exportContext ? exportContext.caseId : "none").data
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
  const persistView = exportContext && !independentFilters
  const view = { ...emptyView, ...(persistView ? savedView : localView) }
  const setView = persistView ? setSavedView : setLocalView
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
  const knownScope = knownPaymentAccounts(
    accountDirectory.isError ? [] : (accountDirectory.data?.items ?? []),
    { ...exportContext?.params, ...accountScope },
    sourceDocumentId
      ? [sourceDocumentId]
      : importBatchId
        ? importSourceIds
        : undefined
  )
  const knownAccounts = knownScope.accounts.filter(
    (account) =>
      (!currency || account.currency === currency) &&
      (!view.analysisGroup ||
        knownAccountGroup(account) === view.analysisGroup) &&
      (!view.analysisPeriod ||
        (view.analysisPeriod !== "undated" &&
          account.periods.some(
            (period) =>
              period.start &&
              period.end &&
              period.start.slice(0, 7) <= view.analysisPeriod &&
              period.end.slice(0, 7) >= view.analysisPeriod
          )))
  )
  const currencyOptions = [
    ...new Set(
      [
        ...transactions.map((row) => row.currency),
        ...knownScope.accounts.map((account) => account.currency),
      ].filter(Boolean)
    ),
  ].sort()
  const unknownDateCount = knownScope.unknownDateAccounts.filter(
    (account) => !currency || account.currencies.includes(currency)
  ).length
  const internal = internalActivity(
    transactions.filter((row) => matchesAccountSelection(row, accountScope)),
    trails.data?.trails ?? []
  )
  const judgementsOf = useRowJudgementLookup()
  const judgementMap = useJudgementRowMap(
    judgementsOf ? exportContext?.caseId : undefined
  )
  const judgementFilter = {
    category: view.judgementCategory,
    strength: view.judgementStrength,
    origin: view.judgementOrigin,
    status: view.judgementStatus,
  }
  const judgementSubFilters =
    Object.values(judgementFilter).filter(Boolean).length
  const judgementWanted = view.judgement || (judgementSubFilters ? "any" : "")
  const matchingCalls = (
    row: LedgerTransaction,
    except?: keyof typeof judgementFilter
  ) =>
    (judgementsOf?.(row) || []).filter((judgement: Judgement) =>
      (Object.keys(judgementFilter) as (keyof typeof judgementFilter)[]).every(
        (key) =>
          key === except ||
          !judgementFilter[key] ||
          judgement[key] === judgementFilter[key]
      )
    )
  const judgementMatches = (row: LedgerTransaction) =>
    !judgementsOf ||
    !judgementWanted ||
    (judgementWanted === "none"
      ? !(judgementsOf(row) || []).length
      : matchingCalls(row).length > 0)
  const preRows = transactions.filter(
    (row) =>
      !invalidRange &&
      (view.activity === "all" ||
        (!!trails.data &&
          !trails.error &&
          activityAmount(row, view.activity, internal) > 0n)) &&
      matchesAccountSelection(row, accountScope) &&
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
  const scopeRows = preRows.filter(judgementMatches)
  const baseRows = scopeRows.filter((row) => matchesCategories(row, categories))
  const categoryBar = exportContext && (
    <PaymentCategoryFilter
      caseId={exportContext.caseId}
      rows={investigation ? filterAnalysis(scopeRows, view) : scopeRows}
      value={categories}
      onChange={setCategories}
      onManage={canEdit ? () => setManageCategories(true) : undefined}
    />
  )
  const categoryRows = preRows.filter((row) =>
    matchesCategories(row, categories)
  )
  // Payments per choice of each judgement sub-filter, under the other active filters (as the queue counts issues).
  const judgementCounts = (key: keyof typeof judgementFilter) => {
    const counts = new Map<string, number>()
    for (const row of categoryRows) {
      const values = new Set(
        matchingCalls(row, key).map((judgement) => judgement[key])
      )
      for (const value of values)
        counts.set(value, (counts.get(value) || 0) + 1)
    }
    return counts
  }
  const touchedRows = categoryRows.filter(
    (row) => (judgementsOf?.(row) || []).length > 0
  ).length
  const judgementsLink = exportContext
    ? `/cases/${exportContext.caseId}/financial?${new URLSearchParams({
        view: "statements",
        judgements: "1",
        ...(view.judgementCategory ? { jType: view.judgementCategory } : {}),
        ...(view.judgementStrength
          ? { jStrength: view.judgementStrength }
          : {}),
        ...(view.judgementOrigin ? { jBy: view.judgementOrigin } : {}),
        jStatus: view.judgementStatus || "all",
      })}`
    : undefined
  const analysisAmounts = (entries: LedgerTransaction[]) =>
    entries.map((row) => ({
      ...row,
      amount_minor: String(activityAmount(row, view.activity, internal)),
    }))
  let rows = investigation ? filterAnalysis(baseRows, view) : baseRows
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
  // Every payment in view before "Not identified only", so a payment just named stays open beside the table.
  const namingRows = rows
  const unnamedRows = investigation && exportContext ? rows.filter(needsName) : []
  // Names Claude read for a person that no person has confirmed: shown as Claude's until confirmed.
  const unconfirmedRows = investigation && exportContext ? rows.filter(needsConfirm) : []
  if (view.unnamedOnly && investigation && exportContext) rows = unnamedRows
  else if (view.unconfirmedOnly && investigation && exportContext) rows = unconfirmedRows
  const index = Math.min(
    page,
    Math.max(0, Math.ceil(rows.length / pageSize) - 1)
  )
  // Open a payment beside the table for naming, and turn the table to the page it is on.
  const openNaming = (id: string, mode?: "name" | "confirm") => {
    if (mode) setNamingMode(mode)
    setNaming(id)
    const at = rows.findIndex((row) => row.key === id)
    if (at >= 0 && Math.floor(at / pageSize) !== index)
      setView((previous) => ({ ...previous, page: Math.floor(at / pageSize) }))
  }
  const transactionToolbar = (
    <div
      ref={toolbarRef}
      className="sticky top-0 z-20 max-h-[55vh] overflow-y-auto rounded border bg-background p-3 shadow-sm"
      role="region"
      aria-label="Transaction tools and filters"
    >
      <div className="flex flex-wrap items-end gap-3">
        {investigation && exportContext && (
          <label>
            Activity
            <select
              className="block rounded border bg-background p-2"
              value={view.activity}
              onChange={(e) => changeView({ activity: e.target.value })}
            >
              <option value="all">All activity</option>
              <option value="external">
                External activity (exclude reviewed internal pairs)
              </option>
              <option value="internal">Reviewed internal transfers</option>
            </select>
          </label>
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
        {investigation && (
          <div className="w-full text-xs text-muted-foreground">
            {trails.error ? (
              <p role="alert">
                Transfer review is unavailable.{" "}
                {view.activity !== "all"
                  ? "Results are withheld until it can be checked."
                  : "All activity remains visible."}{" "}
                <button
                  className="underline"
                  onClick={() => void trails.refetch()}
                >
                  Retry transfer review
                </button>
              </p>
            ) : (
              <>
                <p>
                  Internal movement across the selected accounts:{" "}
                  {[...internal.movements]
                    .map(
                      ([unit, value]) =>
                        `${correctionMoney(String(value), unit.split(" ")[0])}${unit.includes(" ") ? ` ${unit.split(" ")[1]}` : ""}`
                    )
                    .join(" · ") || "No reviewed pairs"}
                  . Both statement entries remain available in All activity.
                </p>
                <p>
                  Only assigned principal from current, reviewed common-owner
                  transfers with all principal accounts in scope is excluded
                  from external activity. Fees and unassigned amounts remain
                  included. Other payments remain included; this is not a claim
                  that all internal transfers have been identified.
                  {internal.pending > 0
                    ? ` ${internal.pending} saved links are one-sided in this view, unconfirmed or need review.`
                    : ""}
                </p>
              </>
            )}
          </div>
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
        <Disclosure
          className="rounded border p-2 text-sm"
          label={
            <>
              Filters
              {[
                currency,
                minimum,
                maximum,
                direction,
                proof,
                judgementWanted,
              ].filter(Boolean).length +
                categories.length >
                0 &&
                ` (${[currency, minimum, maximum, direction, proof, judgementWanted].filter(Boolean).length + categories.length})`}
            </>
          }
        >
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
                {currency && !currencyOptions.includes(currency) && (
                  <option value={currency}>
                    {currency} · not in current account/date scope
                  </option>
                )}
                {currencyOptions.map((c) => (
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
                setCategories([])
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
            {judgementsOf && (
              <fieldset
                className="flex basis-full flex-wrap items-end gap-3 rounded border p-2"
                aria-label="Judgement calls filter"
              >
                <legend className="px-1 text-sm font-medium">
                  Judgement calls
                </legend>
                <label>
                  Payments
                  <select
                    aria-label="Judgement calls"
                    className="block rounded border bg-background p-2"
                    value={view.judgement}
                    onChange={(e) =>
                      changeView({
                        judgement: e.target.value,
                        ...(e.target.value === "none"
                          ? {
                              judgementCategory: "",
                              judgementStrength: "",
                              judgementOrigin: "",
                              judgementStatus: "",
                            }
                          : {}),
                        page: 0,
                      })
                    }
                  >
                    <option value="">All payments</option>
                    <option value="any">
                      With a judgement call ({touchedRows})
                    </option>
                    <option value="none">
                      Without a judgement call ({preRows.length - touchedRows})
                    </option>
                  </select>
                </label>
                {(
                  [
                    [
                      "judgementCategory",
                      "category",
                      "Type",
                      "All types",
                      Object.fromEntries(
                        (judgementMap.data?.categories || []).map((c) => [
                          c.key,
                          c.label,
                        ])
                      ),
                    ],
                    [
                      "judgementStrength",
                      "strength",
                      "Strength",
                      "Inferred and checked guesses",
                      STRENGTH_LABELS,
                    ],
                    [
                      "judgementOrigin",
                      "origin",
                      "Made by",
                      "Agent and processor",
                      ORIGIN_LABELS,
                    ],
                    [
                      "judgementStatus",
                      "status",
                      "Checked",
                      "Checked or not",
                      STATUS_LABELS,
                    ],
                  ] as const
                ).map(([field, key, label, allLabel, labels]) => {
                  const counts = judgementCounts(key)
                  return (
                    <label key={field}>
                      {label}
                      <select
                        aria-label={`Judgement ${label.toLowerCase()}`}
                        className="block rounded border bg-background p-2"
                        disabled={view.judgement === "none"}
                        value={view[field]}
                        onChange={(e) =>
                          changeView({ [field]: e.target.value, page: 0 })
                        }
                      >
                        <option value="">{allLabel}</option>
                        {Object.entries(labels as Record<string, string>).map(
                          ([value, text]) => (
                            <option key={value} value={value}>
                              {text} ({counts.get(value) || 0})
                            </option>
                          )
                        )}
                      </select>
                    </label>
                  )
                })}
                {judgementsLink && (
                  <a className="text-sm underline" href={judgementsLink}>
                    See all judgement calls
                  </a>
                )}
              </fieldset>
            )}
            <Disclosure label="Technical filter">
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
            </Disclosure>
            <p className="basis-full text-xs text-muted-foreground">
              Choose a currency to filter by amount.
            </p>
          </div>
        </Disclosure>
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
      {!investigation && categoryBar}
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
        {categories.map((name) => (
          <Button
            key={name}
            size="sm"
            variant="outline"
            onClick={() =>
              setCategories(categories.filter((other) => other !== name))
            }
          >
            {name} ×
          </Button>
        ))}
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
      {judgementsOf &&
        !judgementWanted &&
        rows.some((row) => (judgementsOf(row) || []).length) && (
          <p
            className="text-xs text-muted-foreground"
            data-testid="ledger-judgement-line"
          >
            Includes{" "}
            {rows
              .filter((row) => (judgementsOf(row) || []).length)
              .length.toLocaleString()}{" "}
            payments touched by judgement calls.{" "}
            <button
              type="button"
              className="underline"
              onClick={() => changeView({ judgement: "any", page: 0 })}
            >
              Show only them
            </button>
          </p>
        )}
      {investigation && exportContext && (
        <>
          <TransactionsOverview
            caseId={exportContext.caseId}
            rows={analysisAmounts(rows)}
            monthRows={analysisAmounts(
              filterAnalysis(baseRows, { ...view, analysisPeriod: "" })
            )}
            tileRows={analysisAmounts(filterAnalysis(scopeRows, view))}
            colors={categoryColors}
            categories={categories}
            onCategories={setCategories}
            activeMonth={view.analysisPeriod}
            onMonth={(analysisPeriod) => changeView({ analysisPeriod })}
            onGroup={(kind, group) => {
              if (kind === "statement")
                changeView({
                  sourceDocumentId: group.key,
                  sourceFilename: group.label,
                })
              else {
                const next =
                  kind === "holder"
                    ? {
                        ...accountScope,
                        accountHolders: group.key ? [group.key] : [],
                      }
                    : {
                        ...accountScope,
                        accountId: undefined,
                        accountIds: [group.key],
                      }
                retainPaymentTableView(exportContext.caseId, accountScope, next)
                applyAccountScope(next)
              }
            }}
            onCategorise={
              canEdit
                ? (pending) => {
                    setEditNames(false)
                    setFullEditor(false)
                    setWalk(null)
                    setLabelIds(pending.map((row) => row.key))
                  }
                : undefined
            }
          />
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <strong>
              <span>
                {rows.length.toLocaleString()} of{" "}
                {transactions.length.toLocaleString()} imported transactions
              </span>
              {exportContext.profile
                ? " in this profile"
                : Object.values(exportContext.params).some((value) =>
                      Array.isArray(value) ? value.length : value
                    )
                  ? " in the current account/date scope"
                  : " in this case"}
            </strong>
            <span className="text-xs text-muted-foreground">
              Totals and analysis include every matching transaction, across all
              pages.
            </span>
          </div>
          {(() => {
            // Every set filter as a removable chip: a filter behind "Filters" is never invisible.
            const judgementNames: Record<string, Record<string, string>> = {
              judgementCategory: Object.fromEntries((judgementMap.data?.categories || []).map((c) => [c.key, c.label])),
              judgementStrength: STRENGTH_LABELS,
              judgementOrigin: ORIGIN_LABELS,
              judgementStatus: STATUS_LABELS,
            }
            const accountName = (id: string) =>
              transactions.find((row) => row.account_id === id)?.account_label || `Account ${id.slice(0, 8)}`
            const chips: [string, string, () => void][] = [
              ...(accountScope.accountHolders || []).map((holder): [string, string, () => void] => [
                `holder:${holder}`,
                `Person: ${holder.replace(/^party:/, "")}`,
                () => applyAccountScope({ ...accountScope, accountHolders: (accountScope.accountHolders || []).filter((h) => h !== holder) }),
              ]),
              ...(accountScope.accountIds || []).map((id): [string, string, () => void] => [
                `account:${id}`,
                `Account: ${accountName(id)}`,
                () => applyAccountScope({ ...accountScope, accountIds: (accountScope.accountIds || []).filter((a) => a !== id) }),
              ]),
              ...(accountScope.accountId && !accountScope.accountIds?.length
                ? [["account-one", `Account: ${accountName(accountScope.accountId)}`, () => applyAccountScope({ ...accountScope, accountId: undefined })] as [string, string, () => void]]
                : []),
              ...(accountScope.startDate ? [["from", `From ${accountScope.startDate}`, () => applyAccountScope({ ...accountScope, startDate: undefined })] as [string, string, () => void]] : []),
              ...(accountScope.endDate ? [["to", `To ${accountScope.endDate}`, () => applyAccountScope({ ...accountScope, endDate: undefined })] as [string, string, () => void]] : []),
              ...(sourceDocumentId ? [["statement", `Statement: ${sourceFilename || sourceDocumentId.slice(0, 8)}`, () => changeView({ sourceDocumentId: "", sourceFilename: "" })] as [string, string, () => void]] : []),
              ...(importBatchId
                ? [["batch", `Import batch · ${importStatementCount} statements`, () => changeView({ importBatchId: "", importBatchRevision: "", importSourceIds: [], importStatementCount: 0 })] as [string, string, () => void]]
                : []),
              ...(search ? [["search", `${searchMode === "boolean" ? "Boolean search" : "Search"}: “${search.length > 30 ? `${search.slice(0, 29)}…` : search}”`, () => changeView({ search: "" })] as [string, string, () => void]] : []),
              ...(view.activity && view.activity !== "all"
                ? [["activity", view.activity === "internal" ? "Reviewed internal transfers" : "External activity", () => changeView({ activity: "all" })] as [string, string, () => void]]
                : []),
              ...(currency ? [["currency", currency, () => changeView({ currency: "", minimum: "", maximum: "" })] as [string, string, () => void]] : []),
              ...(minimum ? [["min", `At least ${minimum}${currency ? ` ${currency}` : ""}`, () => changeView({ minimum: "" })] as [string, string, () => void]] : []),
              ...(maximum ? [["max", `At most ${maximum}${currency ? ` ${currency}` : ""}`, () => changeView({ maximum: "" })] as [string, string, () => void]] : []),
              ...(direction ? [["direction", direction === "credit" ? "Incoming" : "Outgoing", () => changeView({ direction: "" })] as [string, string, () => void]] : []),
              ...(proof ? [["proof", `How it was read: ${readProofClass(proof).label}`, () => changeView({ proof: "" })] as [string, string, () => void]] : []),
              ...(view.judgement
                ? [["judgement", view.judgement === "none" ? "Without a judgement call" : "With a judgement call", () => changeView({ judgement: "", judgementCategory: "", judgementStrength: "", judgementOrigin: "", judgementStatus: "" })] as [string, string, () => void]]
                : []),
              ...(["judgementCategory", "judgementStrength", "judgementOrigin", "judgementStatus"] as const)
                .filter((field) => view[field])
                .map((field): [string, string, () => void] => [
                  field,
                  `Judgement call: ${judgementNames[field][view[field]] || view[field]}`,
                  () => changeView({ [field]: "" }),
                ]),
            ]
            if (!chips.length) return null
            return (
              <div className="flex flex-wrap items-center gap-1.5 text-[13px]" role="group" aria-label="Active filters">
                <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                  {chips.length} active
                </span>
                {chips.map(([key, label, clear]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={clear}
                    aria-label={`Remove filter ${label}`}
                    className="inline-flex items-center gap-1.5 rounded-full bg-[#14161b] px-3 py-1 font-medium text-white hover:bg-[#2a2d35] dark:bg-[#f7f7f8] dark:text-[#0b0c0f]"
                  >
                    {label} <span aria-hidden="true">×</span>
                  </button>
                ))}
              </div>
            )
          })()}
          {categoryBar}
          <AnalysisFilterChips filters={view} onChange={changeView} />
          <PaymentTotals
            rows={analysisAmounts(rows)}
            knownAccounts={knownAccounts}
            caseId={exportContext.caseId}
            label={
              view.activity === "all"
                ? "Payments matching your filters"
                : "Assigned amounts matching your activity filter"
            }
          />
          {accountDirectory.isError && !exportContext.profile && (
            <p role="alert" className="text-xs">
              Known account details could not be loaded. These totals currently
              show accounts with matching imported payments only.
            </p>
          )}
          {unknownDateCount > 0 && (
            <p className="text-xs text-muted-foreground">
              {unknownDateCount} known accounts have no usable saved statement
              dates for this range. Their matching payments, if any, are still
              counted. Clear the date range to include their account context.
            </p>
          )}
          {view.activity !== "all" && (
            <p className="text-xs text-muted-foreground">
              Totals and charts show{" "}
              {view.activity === "internal"
                ? "assigned internal principal"
                : "amounts outside assigned internal principal, including fees and unassigned portions"}
              . The table and transaction downloads retain each original entry
              in full; a split entry can appear in both activity views.
            </p>
          )}
          {transactionToolbar}
          {sort.startsWith("amount") && mixedCurrencies && (
            <p className="text-xs text-muted-foreground">
              Sorted by amount size across currencies. Money in or out does not
              change this order; currencies are not converted.
            </p>
          )}
          <TransactionAnalysisPanels
            hideControls
            rows={analysisAmounts(baseRows)}
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
              <div
                role="group"
                aria-label="Show payments as"
                className="inline-flex rounded-lg bg-muted p-[3px] text-[13px]"
              >
                {(
                  [
                    [false, "Cards"],
                    [true, "Table view"],
                  ] as const
                ).map(([on, name]) => (
                  <button
                    key={name}
                    type="button"
                    aria-pressed={tableView === on}
                    onClick={() => {
                      setTableView(on)
                      storeTableView(on)
                    }}
                    className={`rounded-md px-3 py-1 ${tableView === on ? "bg-background font-semibold shadow-sm" : "font-medium text-muted-foreground hover:text-foreground"}`}
                  >
                    {name}
                  </button>
                ))}
              </div>
              {tableView && (
                <TableColumnPicker
                  columns={tableColumns}
                  onChange={(next) => {
                    setTableColumns(next)
                    storeTableColumns(next)
                  }}
                />
              )}
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
                  {exportContext && (
                    <MoneyTrailReview
                      caseId={exportContext.caseId}
                      transactionIds={selection}
                      label="Link transfer or money trail"
                    />
                  )}
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
                          setFullEditor(false)
                          setWalk(null)
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
                <Disclosure className="text-sm" label="Selected amounts and saved selections">
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
                </Disclosure>
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
      {labelIds && exportContext && !editNames && !fullEditor && (
        <CategorisePaymentDialog
          key={labelIds.join(",")}
          caseId={exportContext.caseId}
          ids={labelIds}
          progress={walk && labelIds.length === 1 ? { done: walk.done, total: walk.queue.length } : undefined}
          onNext={walk && labelIds.length === 1 ? () => {
            const next = walk.queue[walk.queue.indexOf(labelIds[0]) + 1]
            setWalk({ ...walk, done: walk.done + 1 })
            if (next) setLabelIds([next])
            else {
              setLabelIds(null)
              setWalk(null)
            }
          } : undefined}
          onSkip={walk && labelIds.length === 1 ? () => {
            const next = walk.queue[walk.queue.indexOf(labelIds[0]) + 1]
            if (next) setLabelIds([next])
            else {
              setLabelIds(null)
              setWalk(null)
            }
          } : undefined}
          onMoreFields={() => setFullEditor(true)}
          onManage={() => setManageCategories(true)}
          onSaved={(replacements) => {
            const mapping = new Map(
              replacements.map((row) => [row.previous_id, row.id])
            )
            setSelection((previous) =>
              previous.map((id) => mapping.get(id) ?? id)
            )
          }}
          onClose={() => {
            setLabelIds(null)
            setWalk(null)
          }}
        />
      )}
      {labelIds && exportContext && (editNames || fullEditor) && (
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
          onClose={() => {
            setLabelIds(null)
            setFullEditor(false)
            setWalk(null)
          }}
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
      {investigation && exportContext && (unnamedRows.length > 0 || view.unnamedOnly) && (
        <div
          className="flex flex-wrap items-center gap-2 rounded border bg-card px-3 py-2 text-sm"
          role="group"
          aria-label="Payments without a name"
        >
          <span role="status">
            <strong>{unnamedRows.length.toLocaleString()}</strong>{" "}
            {unnamedRows.length === 1 ? "payment" : "payments"} in view with
            the other side not identified
          </span>
          <Button
            size="sm"
            variant="outline"
            aria-pressed={view.unnamedOnly}
            onClick={() => changeView({ unnamedOnly: !view.unnamedOnly, unconfirmedOnly: false })}
          >
            {view.unnamedOnly ? "Show all payments" : "Show only these"}
          </Button>
          {unnamedRows.length > 0 && (
            <Button
              size="sm"
              onClick={() => {
                const first = unnamedRows.find((row) =>
                  rows.slice(index * pageSize, (index + 1) * pageSize).includes(row)
                ) ?? unnamedRows[0]
                openNaming(first.key, "name")
              }}
            >
              {canEdit ? "Name them one by one" : "See their statement lines one by one"}
            </Button>
          )}
        </div>
      )}
      {investigation && exportContext && (unconfirmedRows.length > 0 || view.unconfirmedOnly) && (
        <div
          className="flex flex-wrap items-center gap-2 rounded border border-[#e7c66b] bg-[#fdf6dd] px-3 py-2 text-sm text-[#5c3d00] dark:bg-amber-950 dark:text-amber-100"
          role="group"
          aria-label="Names read by Claude, not confirmed"
        >
          <span role="status">
            <strong>{unconfirmedRows.length.toLocaleString()}</strong>{" "}
            {unconfirmedRows.length === 1 ? "name" : "names"} in view read
            by Claude and not confirmed by a person
          </span>
          <Button
            size="sm"
            variant="outline"
            aria-pressed={view.unconfirmedOnly}
            onClick={() =>
              changeView({ unconfirmedOnly: !view.unconfirmedOnly, unnamedOnly: false })
            }
          >
            {view.unconfirmedOnly ? "Show all payments" : "Show only these"}
          </Button>
          {canEdit && unconfirmedRows.length > 0 && (
            <Button
              size="sm"
              onClick={() => {
                const first = unconfirmedRows.find((row) =>
                  rows.slice(index * pageSize, (index + 1) * pageSize).includes(row)
                ) ?? unconfirmedRows[0]
                openNaming(first.key, "confirm")
              }}
            >
              Confirm them one by one
            </Button>
          )}
        </div>
      )}
      <div
        className={
          naming && exportContext
            ? "grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(400px,0.85fr)]"
            : ""
        }
      >
      <div className="min-w-0">
      {!rows.length ? (
        <p>
          No payments match these filters. Clear the filters or choose another
          account/date range.
        </p>
      ) : investigation && exportContext && !tableView ? (
        <PaymentCardList
          findings={findings.data}
          categoryColors={categoryColors}
          rows={rows.slice(index * pageSize, (index + 1) * pageSize)}
          selected={selection}
          expanded={view.expandedRows}
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
                  setFullEditor(false)
                  setWalk({ queue: rows.map((item) => item.key), done: 0 })
                  setLabelIds([row.key])
                }
              : undefined
          }
          onName={(row) => openNaming(row.key, canEdit && needsConfirm(row) ? "confirm" : "name")}
          nameAction={canEdit ? "Name it" : "See the line"}
          onParty={(side, key) => {
            const field = side === "from" ? "fromNames" : "toNames"
            changeView({
              [field]: view[field].includes(key)
                ? view[field].filter((n) => n !== key)
                : [...view[field], key],
            })
          }}
        />
      ) : investigation && exportContext ? (
        <TransactionExplorerTable
          columns={tableColumns}
          statementNames={tableStatementNames}
          findings={findings.data}
          categoryColors={categoryColors}
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
                  setFullEditor(false)
                  setWalk({ queue: rows.map((item) => item.key), done: 0 })
                  setLabelIds([row.key])
                }
              : undefined
          }
          onName={(row) => openNaming(row.key, canEdit && needsConfirm(row) ? "confirm" : "name")}
          nameAction={canEdit ? "Name it" : "See the line"}
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
      </div>
      {naming && exportContext && (
        // Beside the table (xl) the panel sticks just below the sticky tools bar; above it, it scrolls with the page.
        <div className="order-first min-w-0 xl:sticky xl:order-none" style={{ top: toolbarHeight + 8 }}>
          <PaymentNamingPanel
            key={exportContext.caseId}
            caseId={exportContext.caseId}
            rows={namingRows}
            queue={namingMode === "confirm" ? unconfirmedRows : unnamedRows}
            mode={namingMode}
            currentId={naming}
            onMove={openNaming}
            onClose={() => setNaming(null)}
            onOpenDetails={actions.onSource}
            readOnly={!canEdit}
            stickyTop={toolbarHeight}
          />
        </div>
      )}
      </div>
      {exportContext && !invalidRange && (
        <Disclosure
          className="rounded border p-3"
          label={<>Download these transactions</>}
        >
          <LedgerExportButton
            caseId={exportContext.caseId}
            params={{ ...exportContext.params, ...accountScope }}
            tableView={{
              ...analysisTableView(view),
              ...(exportContext.profile
                ? {
                    profile_id: exportContext.profile.id,
                    profile_group: exportContext.profile.group,
                    ...(exportContext.profile.scope
                      ? { profile_scope: exportContext.profile.scope }
                      : {}),
                  }
                : {}),
              search,
              search_mode: searchMode as "text" | "boolean",
              ...(categories.length === 1
                ? { category: categories[0] }
                : categories.length
                  ? { categories }
                  : {}),
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
        </Disclosure>
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
import { MoneyTrailReview } from "./MoneyTrailReview"
