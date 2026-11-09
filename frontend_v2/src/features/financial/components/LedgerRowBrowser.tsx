import { AddToTimelineDialog } from "@/features/timeline/components/AddToTimelineDialog"
import { CheckTag } from "@/lib/data-colour"
import { useMoneyTrails } from "../hooks/use-money-trails"
import { internalActivity, activityAmount } from "../lib/money-trails"
import { correctionMoney } from "../lib/correction-contract"
import { matchesAccountSelection } from "../lib/account-selection"
import { compareDisplayedAmounts } from "../lib/transaction-search"
import { transactionSearch } from "../lib/transaction-search"
import { InAppLink } from "./InAppLink"
import {
  ControlGroup,
  SectionSwitch,
  TransactionControlPanel,
} from "./TransactionControlPanel"
import {
  TRANSACTION_SECTIONS,
  useControlsOpen,
  useTransactionSections,
} from "../lib/transaction-sections"
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
  analysisFilterCount,
  analysisTableView,
  filterAnalysis,
  sortAnalysisRows,
} from "../lib/transaction-analysis"
import { PaymentEditsEditor } from "./PaymentEditsEditor"
import { CategorisePaymentDialog } from "./CategorisePaymentDialog"
import { PaymentCategoryManager } from "./PaymentCategoryManager"
import { TransactionAccountFilters } from "./TransactionAccountFilters"
import { WorkspaceScope } from "./InvestigationWorkspaceParts"
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
import { AddPaymentsToFinding } from "./AddPaymentsToFinding"
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
import { RowJudgements, useRowJudgementLookup } from "../hooks/use-judgement-rows"
import { useJudgementRowMap } from "../hooks/use-judgements"
import {
  PRIORITY_LABELS,
  STATUS_LABELS,
  STRENGTH_LABELS,
  ORIGIN_LABELS,
  topPriority,
  type Judgement,
} from "../lib/judgements"
import { PriorityLegend } from "./JudgementCalls"
import { ledgerTransactionsQuery, type LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { FIRST_VIEW_PAGE_SIZES, useLedgerFirstView } from "../hooks/use-ledger-first-view"
import { whenSettled } from "../lib/page-speed"
import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useContext, useEffect, useMemo, useRef, useState, type ComponentProps, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { LedgerTable } from "./LedgerTable"
import { paymentFilterKey } from "../lib/payment-table-draft"
import { AddToTheory } from "@/features/theory/AddToTheory"
import { PaymentNamingPanel } from "./PaymentNamingPanel"
import { ReadingCheckContext, showReadingRow } from "../hooks/reading-check-context"
import { needsConfirm, needsName, unconfirmedNamesLabel } from "../lib/payment-naming"
import { BulkConfirmReadings } from "./BulkConfirmReadings"
import type { LedgerTransaction } from "../api"
const TABLE_VIEW_KEY = "financial-transactions-table-view"
// The first view's rows before it arrives (one value, so memos over the rows do not recompute each render).
const NO_ROWS: LedgerTransaction[] = []
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
  transactions: allTransactions,
  exportContext,
  investigation = false,
  independentFilters = false,
  firstView,
  ...actions
}: ComponentProps<typeof LedgerTable> & {
  investigation?: boolean
  independentFilters?: boolean
  /**
   * Given while every row has not been read (LedgerPanel, Transactions page): the default view is drawn from the
   * server's first view (one page of rows and the figures above them); anything that needs every row calls
   * `onNeedAll` and waits for them, saying what it is reading (`loading`).
   */
  firstView?: {
    params: LedgerQueryParams | undefined
    readingAll: boolean
    /** Shown in place of the page while nothing has been shown yet (with the date range). */
    loading: ReactNode
    /** The reading line alone, shown in place of the figures and list once the page is on screen. */
    status: ReactNode
    onNeedAll: () => void
  }
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
  const [addToFinding, setAddToFinding] = useState(false)
  const [finding, setFinding] = useState<"question" | "observation" | null>(
    null
  )
  const [reviewSelection, setReviewSelection] = useState(false)
  const [localView, setLocalView] = useState(emptyView)
  // Page switches remembered for this person (control panel); a new visit's analysis panels start from them.
  const [sections, setSection] = useTransactionSections()
  const [savedView, setSavedView] = useFinancialDraft(
    exportContext?.caseId ?? "none",
    paymentTableDraftName(exportContext?.params, investigation) +
      (exportContext?.profile
        ? `:profile:${JSON.stringify(exportContext.profile)}`
        : ""),
    exportContext?.profile
      ? { ...emptyView, chartsOpen: true }
      : investigation
        ? { ...emptyView, chartsOpen: sections.charts, partiesOpen: sections.parties, flowOpen: sections.flow }
        : emptyView
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
  // The control panel (Transactions page): every filter and page switch, docked on the right.
  const [controlsOpen, setControlsOpen] = useControlsOpen()
  const queryClient = useQueryClient()
  // The default view (no filter, search, category, account choice, judgement filter, selection, open panel or
  // section beyond the totals, ledger order) is drawn from the server's first view: the same figures over the same
  // rows, without reading every payment. Anything else waits for every row.
  const firstViewEligible =
    !!firstView &&
    !!exportContext &&
    !exportContext.profile &&
    investigation &&
    paymentFilterKey(view) === paymentFilterKey(emptyView) &&
    !view.unnamedOnly &&
    !view.unconfirmedOnly &&
    !view.chartsOpen &&
    !view.partiesOpen &&
    !view.flowOpen &&
    !sections.months &&
    !sections.breakdown &&
    !sections.accountTotals &&
    categories.length === 0 &&
    !accountScope.accountId &&
    !accountScope.accountIds?.length &&
    !accountScope.accountHolders?.length &&
    selection.length === 0 &&
    !controlsOpen &&
    !tableView &&
    FIRST_VIEW_PAGE_SIZES.includes(pageSize) &&
    !naming &&
    !walk &&
    !labelIds &&
    !editNames &&
    !manageCategories &&
    !notesCsv &&
    !timeline &&
    !compare &&
    !finding &&
    !reviewSelection
  const first = useLedgerFirstView(
    firstViewEligible ? exportContext?.caseId : undefined,
    firstView?.params,
    page,
    pageSize
  )
  const firstData = firstViewEligible && first.data?.available && first.data.total > 0 ? first.data : null
  // Actions that need every row (CSV, select all, the naming walk) wait for them, then run with them.
  const [pendingAction, setPendingAction] = useState<{ kind: string; key?: string } | null>(null)
  const needAll = (action: { kind: string; key?: string }) => {
    setPendingAction(action)
    firstView?.onNeedAll()
  }
  const firstViewFailed =
    !!firstView && firstViewEligible && (first.isError || (!!first.data && (!first.data.available || first.data.total === 0)))
  const onNeedAll = firstView?.onNeedAll
  const readingAll = !!firstView?.readingAll
  useEffect(() => {
    if (onNeedAll && !readingAll && (!firstViewEligible || firstViewFailed || pendingAction)) onNeedAll()
  }, [onNeedAll, readingAll, firstViewEligible, firstViewFailed, pendingAction])
  // Once the first view is on screen and nothing else is loading, every row is read into the cache in the
  // background, so a filter or search a moment later does not wait for them. The page keeps the first view.
  const prefetchCase = firstData ? exportContext?.caseId : undefined
  const prefetchParams = firstView?.params
  useEffect(() => {
    if (!prefetchCase) return
    const signal = { cancelled: false }
    let timer: ReturnType<typeof setTimeout> | undefined
    void whenSettled(queryClient, signal).then((at) => {
      if (at === null || signal.cancelled) return
      timer = setTimeout(() => void queryClient.prefetchQuery(ledgerTransactionsQuery(prefetchCase, prefetchParams)), 500)
    })
    return () => {
      signal.cancelled = true
      if (timer) clearTimeout(timer)
    }
    // By value: the scope object may be rebuilt on each render while it says the same.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefetchCase, JSON.stringify(prefetchParams ?? null), queryClient])
  const transactions = firstView ? (firstData?.rows ?? NO_ROWS) : allTransactions
  // Once the page is on screen it stays mounted (search box, controls, scroll) while every row or the next page is
  // read; only the figures and the list wait, since without the rows they would count nothing or one page.
  const shownOnce = useRef(false)
  if (firstData) shownOnce.current = true
  const waiting = !!firstView && !firstData
  const selectedIds = new Set(selection)
  const selectedHere = transactions.filter((row) => selectedIds.has(row.key))
  const toggle = (row: LedgerTransaction, checked: boolean) =>
    setSelection((previous) =>
      checked
        ? [...new Set([...previous, row.key])]
        : previous.filter((id) => id !== row.key)
    )
  // Which payments match depends on the filters only. Showing or hiding a section, opening a row or turning
  // the page changes none of it, so the passes over every payment below run once per change of the filters,
  // not on every click: on a case with tens of thousands of payments each pass took seconds, and a section
  // toggle looked dead until it finished.
  const filterKey = paymentFilterKey(view)
  const searchResult = useMemo(
    () => transactionSearch(search, searchMode),
    [search, searchMode]
  )
  const minMinor = minimum.trim() ? correctionMinor(minimum, currency) : ""
  const maxMinor = maximum.trim() ? correctionMinor(maximum, currency) : ""
  const invalidRange =
    minMinor === null ||
    maxMinor === null ||
    (!!minMinor && !!maxMinor && BigInt(minMinor) > BigInt(maxMinor))
  const batchSources = new Set(importSourceIds)
  const scopeParamsKey = JSON.stringify(exportContext?.params ?? {})
  const knownScope = useMemo(
    () =>
      knownPaymentAccounts(
        accountDirectory.isError ? [] : (accountDirectory.data?.items ?? []),
        { ...exportContext?.params, ...accountScope },
        sourceDocumentId
          ? [sourceDocumentId]
          : importBatchId
            ? importSourceIds
            : undefined
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [accountDirectory.data, accountDirectory.isError, scopeParamsKey, accountScope, filterKey]
  )
  const knownAccounts = useMemo(() => knownScope.accounts.filter(
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ), [knownScope, filterKey])
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
  const internal = useMemo(
    () =>
      internalActivity(
        transactions.filter((row) => matchesAccountSelection(row, accountScope)),
        trails.data?.trails ?? []
      ),
    [transactions, accountScope, trails.data]
  )
  const judgementsOf = useRowJudgementLookup()
  const judgementContext = useContext(RowJudgements)
  const judgementMap = useJudgementRowMap(
    judgementsOf ? exportContext?.caseId : undefined
  )
  const judgementFilter = {
    priority: view.judgementPriority,
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
          String(judgement[key]) === judgementFilter[key]
      )
    )
  const judgementMatches = (row: LedgerTransaction) =>
    !judgementsOf ||
    !judgementWanted ||
    (judgementWanted === "none"
      ? !(judgementsOf(row) || []).length
      : matchingCalls(row).length > 0)
  const listingCalls = !!judgementsOf && judgementWanted === "any"
  const { preRows, scopeRows, baseRows, categoryRows, namingRows, mixedCurrencies } = useMemo(() => {
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
  const categoryRows = preRows.filter((row) =>
    matchesCategories(row, categories)
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
  // Focus first: in a list of judgement calls the recorded order gives way to the calls' tiers ("Check first" on
  // top), then inferred before checked, then the larger amount; the sort stays stable so dates order each tie.
  const focusFirst = listingCalls && sort === "ledger"
  if (focusFirst) {
    const rank = (row: LedgerTransaction) => {
      const calls = matchingCalls(row)
      return [topPriority(calls) || 9, calls.some((call) => call.strength === "inferred") ? 0 : 1] as const
    }
    const ranks = new Map(rows.map((row) => [row.key, rank(row)]))
    rows.sort((a, b) => {
      const [tierA, strengthA] = ranks.get(a.key)!
      const [tierB, strengthB] = ranks.get(b.key)!
      return tierA - tierB || strengthA - strengthB || -compareDisplayedAmounts(a, b)
    })
  }
  return { preRows, scopeRows, baseRows, categoryRows, namingRows: rows, mixedCurrencies }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transactions, filterKey, accountScope, categories, trails.data, trails.error, internal, judgementsOf, investigation, searchResult, listingCalls])
  // Rows in a list of judgement calls carry their tier's tint, counting only the calls the sub-filters keep.
  const tintedContext = useMemo(
    () =>
      judgementContext && listingCalls
        ? { ...judgementContext, tint: true, calls: (row: LedgerTransaction) => matchingCalls(row) }
        : judgementContext,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [judgementContext, listingCalls, view.judgementPriority, view.judgementCategory, view.judgementStrength,
      view.judgementOrigin, view.judgementStatus]
  )
  // Payments per choice of each judgement sub-filter, under the other active filters (as the queue counts issues).
  const judgementCountsByKey = useMemo(() => {
    const byKey = new Map<keyof typeof judgementFilter, Map<string, number>>()
    if (!judgementsOf) return byKey
    for (const key of Object.keys(judgementFilter) as (keyof typeof judgementFilter)[]) {
      const counts = new Map<string, number>()
      for (const row of categoryRows) {
        const values = new Set(
          matchingCalls(row, key).map((judgement) => judgement[key])
        )
        for (const value of values)
          counts.set(String(value), (counts.get(String(value)) || 0) + 1)
      }
      byKey.set(key, counts)
    }
    return byKey
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoryRows, judgementsOf, filterKey])
  const judgementCounts = (key: keyof typeof judgementFilter) =>
    judgementCountsByKey.get(key) ?? new Map<string, number>()
  const touchedRows = useMemo(
    () =>
      categoryRows.filter((row) => (judgementsOf?.(row) || []).length > 0)
        .length,
    [categoryRows, judgementsOf]
  )
  const judgementsLink = exportContext
    ? `/cases/${exportContext.caseId}/financial?${new URLSearchParams({
        view: "statements",
        judgements: "1",
        ...(view.judgementPriority ? { jPriority: view.judgementPriority } : {}),
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
  // What each section is given, worked out with the rows above (amounts per activity view, as shown).
  const showing = !!(investigation && exportContext)
  const sectionRows = useMemo(
    () => ({
      categoryBar: investigation ? filterAnalysis(scopeRows, view) : scopeRows,
      months: showing
        ? analysisAmounts(filterAnalysis(baseRows, { ...view, analysisPeriod: "" }))
        : [],
      tiles: showing ? analysisAmounts(filterAnalysis(scopeRows, view)) : [],
      analysis: showing ? analysisAmounts(baseRows) : [],
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [scopeRows, baseRows, filterKey, internal, investigation, showing]
  )
  const categoryBar = exportContext && (
    <PaymentCategoryFilter
      caseId={exportContext.caseId}
      rows={sectionRows.categoryBar}
      value={categories}
      onChange={setCategories}
      onManage={canEdit ? () => setManageCategories(true) : undefined}
    />
  )
  const unnamedRows = useMemo(
    () => (showing ? namingRows.filter(needsName) : []),
    [namingRows, showing]
  )
  // Names Claude read for a person that no person has confirmed: shown as Claude's until confirmed.
  const unconfirmedRows = useMemo(
    () => (showing ? namingRows.filter(needsConfirm) : []),
    [namingRows, showing]
  )
  const rows =
    view.unnamedOnly && showing
      ? unnamedRows
      : view.unconfirmedOnly && showing
        ? unconfirmedRows
        : namingRows
  const shownAmounts = useMemo(
    () => (showing ? analysisAmounts(rows) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rows, internal, showing, filterKey]
  )
  const index = firstData
    ? firstData.page
    : Math.min(page, Math.max(0, Math.ceil(rows.length / pageSize) - 1))
  // In the first view the rows are the page itself and the counts are the server's over every row.
  const total = firstData ? firstData.total : rows.length
  const pageRows = firstData ? rows : rows.slice(index * pageSize, (index + 1) * pageSize)
  const unnamedCount = firstData ? firstData.unnamed : unnamedRows.length
  const unconfirmedCount = firstData ? firstData.unconfirmed : unconfirmedRows.length
  // Once shown, the "not confirmed" bar stays (saying all are confirmed) when the last one in view is confirmed:
  // removing it would move every row under it while the person is working there.
  const [readingsShown, setReadingsShown] = useState(false)
  if (unconfirmedCount > 0 && !readingsShown) setReadingsShown(true)
  // Open a payment beside the table for naming, and turn the table to the page it is on.
  const openNaming = (id: string, mode?: "name" | "confirm") => {
    if (mode) setNamingMode(mode)
    setNaming(id)
    const at = rows.findIndex((row) => row.key === id)
    if (at >= 0 && Math.floor(at / pageSize) !== index)
      setView((previous) => ({ ...previous, page: Math.floor(at / pageSize) }))
  }
  // A reading checked inline and opened in the panel: the row it came from, so closing the panel lands back on it.
  const checkedRow = useRef<string | null>(null)
  const showRow = showReadingRow
  const openFromReading = (id: string) => {
    checkedRow.current = id
    const row = rows.find((item) => item.key === id)
    openNaming(id, canEdit && row && needsConfirm(row) ? "confirm" : "name")
    showRow(id, false)
  }
  const closeNaming = () => {
    setNaming(null)
    showRow(checkedRow.current, true)
    checkedRow.current = null
  }
  const readingCheck = useMemo(() => (exportContext ? { openPanel: openFromReading } : {}), [exportContext, rows, canEdit, index, pageSize]) // eslint-disable-line react-hooks/exhaustive-deps
  const [sectionEl, setSectionEl] = useState<HTMLElement | null>(null)
  // The naming panel opens beside the table on the right: the control panel steps back to its tab.
  const [namingSeen, setNamingSeen] = useState(naming)
  if (namingSeen !== naming) {
    setNamingSeen(naming)
    if (naming && controlsOpen) setControlsOpen(false)
  }
  // Every filter in force as a removable chip, so a filter inside the collapsed panel is never invisible.
  const judgementNames: Record<string, Record<string, string>> = {
    judgementCategory: Object.fromEntries((judgementMap.data?.categories || []).map((c) => [c.key, c.label])),
    judgementStrength: STRENGTH_LABELS,
    judgementOrigin: ORIGIN_LABELS,
    judgementStatus: STATUS_LABELS,
    judgementPriority: PRIORITY_LABELS,
  }
  const accountName = (id: string) =>
    transactions.find((row) => row.account_id === id)?.account_label || `Account ${id.slice(0, 8)}`
  const activeChips: [string, string, () => void][] = [
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
      ? [["judgement", view.judgement === "none" ? "Without a judgement call" : "With a judgement call", () => changeView({ judgement: "", judgementPriority: "", judgementCategory: "", judgementStrength: "", judgementOrigin: "", judgementStatus: "" })] as [string, string, () => void]]
      : []),
    ...(["judgementPriority", "judgementCategory", "judgementStrength", "judgementOrigin", "judgementStatus"] as const)
      .filter((field) => view[field])
      .map((field): [string, string, () => void] => [
        field,
        `Judgement call: ${judgementNames[field][view[field]] || view[field]}`,
        () => changeView({ [field]: "" }),
      ]),
    ...categories.map((name): [string, string, () => void] => [
      `category:${name}`,
      `Category: ${name}`,
      () => setCategories(categories.filter((other) => other !== name)),
    ]),
    ...(view.unnamedOnly && investigation && exportContext
      ? [["unnamed", "Only payments with the other side not identified", () => changeView({ unnamedOnly: false })] as [string, string, () => void]]
      : []),
    ...(view.unconfirmedOnly && investigation && exportContext
      ? [["unconfirmed", "Only names read by Claude, not confirmed", () => changeView({ unconfirmedOnly: false })] as [string, string, () => void]]
      : []),
  ]
  const activeFilterCount = activeChips.length + analysisFilterCount(view)
  const touchedInView = judgementsOf && !judgementWanted
    ? firstData
      ? firstData.touched
      : rows.filter((row) => (judgementsOf(row) || []).length).length
    : 0
  const judgementNote = touchedInView > 0 && (
    <p className="text-xs text-muted-foreground" data-testid="ledger-judgement-line">
      Includes {touchedInView.toLocaleString()} payments touched by judgement calls.{" "}
      <button
        type="button"
        className="underline"
        onClick={() => changeView({ judgement: "any", page: 0 })}
      >
        Show only them
      </button>
    </p>
  )
  const chipLine = (
    <div className="flex flex-wrap items-center gap-1.5 text-[13px]" role="group" aria-label="Active filters">
      <strong className="mr-2 text-sm">
        <span>
          {total.toLocaleString()} of {(firstData ? firstData.total : transactions.length).toLocaleString()} imported transactions
        </span>
        {exportContext?.profile
          ? " in this profile"
          : Object.values(exportContext?.params ?? {}).some((value) =>
                Array.isArray(value) ? value.length : value
              )
            ? " in the current account/date scope"
            : " in this case"}
      </strong>
      {activeFilterCount > 0 ? (
        <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
          {activeFilterCount} {activeFilterCount === 1 ? "filter" : "filters"} on
        </span>
      ) : (
        <span className="text-xs text-muted-foreground">No filters on</span>
      )}
      {activeChips.map(([key, label, clear]) => (
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
      <AnalysisFilterChips filters={view} onChange={changeView} />
      {judgementNote && <div className="ml-auto">{judgementNote}</div>}
    </div>
  )
  const activityControl = investigation && exportContext && (
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
  )
  const searchControls = (
    <>
        <label>
          <span className={investigation && exportContext ? "sr-only" : ""}>Search payments</span>
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
          <span className={investigation && exportContext ? "sr-only" : ""}>Search mode</span>
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
    </>
  )
  const internalNote = investigation && (
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
  )
  const csvButtons = investigation && (
          <>
            <Button
              variant="outline"
              size="sm"
              disabled={!total}
              onClick={() =>
                firstData
                  ? needAll({ kind: "csv" })
                  : downloadCsv(
                      transactionCsv(rows),
                      "loupe-filtered-transactions.csv"
                    )
              }
            >
              Download CSV ({total.toLocaleString()})
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
  )
  const filterTotal =
    [currency, minimum, maximum, direction, proof, judgementWanted].filter(Boolean).length + categories.length
  const filterFields = (
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
                <option value="ledger">
                  {listingCalls ? "Check first, then recorded date" : "Recorded date order"}
                </option>
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
                              judgementPriority: "",
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
                {view.judgement !== "none" && (
                  <PriorityLegend
                    className="basis-full"
                    counts={Object.fromEntries(judgementCounts("priority"))}
                    value={view.judgementPriority}
                    onChoose={(value) =>
                      changeView({
                        judgementPriority: value,
                        ...(value && !view.judgement ? { judgement: "any" } : {}),
                        page: 0,
                      })
                    }
                  />
                )}
                {(
                  [
                    [
                      "judgementPriority",
                      "priority",
                      "Priority",
                      "Every priority",
                      PRIORITY_LABELS,
                    ],
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
                  <InAppLink className="text-sm underline" to={judgementsLink}>
                    See all judgement calls
                  </InAppLink>
                )}
              </fieldset>
            )}
            <Disclosure label="Filter by how it was checked">
              <label>
                How it was checked
                <select
                  aria-label="Table check status"
                  className="block rounded border bg-background p-2"
                  value={proof}
                  onChange={(e) => {
                    changeView({ proof: e.target.value })
                  }}
                >
                  <option value="">All</option>
                  {[...new Set(transactions.map((r) => r.proof_class))]
                    .sort()
                    .map((p) => (
                      <option key={p} value={p}>{readProofClass(p).label}</option>
                    ))}
                </select>
              </label>
            </Disclosure>
            <p className="basis-full text-xs text-muted-foreground">
              Choose a currency to filter by amount.
            </p>
          </div>
  )
  const searchHelp = (
    <>
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
    </>
  )
  // Outside the Transactions page (a statement's payments, a profile) every tool stays in one bar above the list.
  const transactionToolbar = (
    <div
      ref={toolbarRef}
      className="sticky top-0 z-20 max-h-[55vh] overflow-y-auto rounded border bg-background p-3 shadow-sm"
      role="region"
      aria-label="Transaction tools and filters"
    >
      <div className="flex flex-wrap items-end gap-3">
        {activityControl}
        {searchControls}
        {internalNote}
        {csvButtons}
        <Disclosure
          className="rounded border p-2 text-sm"
          label={<>Filters{filterTotal > 0 && ` (${filterTotal})`}</>}
        >
          {filterFields}
        </Disclosure>
      </div>
      {searchHelp}
    </div>
  )
  // On the Transactions page the bar above the table holds only search and downloads; every filter and page
  // switch is in the control panel on the right.
  const searchBar = (
    <div
      ref={toolbarRef}
      className="sticky top-0 z-20 rounded-b border bg-background px-3 py-2 shadow-sm"
      role="region"
      aria-label="Transaction tools and filters"
    >
      <div className="flex flex-wrap items-center gap-3">
        {searchControls}
        {!waiting && csvButtons}
        {!waiting && (
        <Button
          variant="outline"
          size="sm"
          disabled={!total || (!firstData && rows.every((row) => selectedIds.has(row.key)))}
          onClick={() =>
            firstData
              ? needAll({ kind: "selectAll" })
              : setSelection((previous) => [...new Set([...previous, ...rows.map((row) => row.key)])])
          }
        >
          Select all {total} matching payments
        </Button>
        )}
        <Button
          variant="outline"
          size="sm"
          aria-expanded={controlsOpen}
          aria-controls="transaction-controls"
          onClick={() => setControlsOpen(!controlsOpen)}
        >
          Controls{activeFilterCount > 0 ? ` (${activeFilterCount} on)` : ""}
        </Button>
      </div>
      {searchHelp}
    </div>
  )
  const nameFirst = () => {
    const first = unnamedRows.find((row) => pageRows.includes(row)) ?? unnamedRows[0]
    if (first) openNaming(first.key, "name")
  }
  const confirmFirst = () => {
    const first = unconfirmedRows.find((row) => pageRows.includes(row)) ?? unconfirmedRows[0]
    if (first) openNaming(first.key, "confirm")
  }
  const startWalk = (key: string) => {
    setWalk({ queue: rows.map((item) => item.key), done: 0 })
    setLabelIds([key])
  }
  // Run with this render's rows: the action asked for in the first view, once every row is here.
  const runPending = useRef<(action: { kind: string; key?: string }) => void>(() => {})
  runPending.current = (action) => {
    if (action.kind === "csv") downloadCsv(transactionCsv(rows), "loupe-filtered-transactions.csv")
    else if (action.kind === "selectAll")
      setSelection((previous) => [...new Set([...previous, ...rows.map((row) => row.key)])])
    else if (action.kind === "nameFirst") nameFirst()
    else if (action.kind === "confirmFirst") confirmFirst()
    else if (action.kind === "walk" && action.key) {
      setEditNames(false)
      setFullEditor(false)
      startWalk(action.key)
    }
  }
  useEffect(() => {
    if (firstView || !pendingAction) return
    runPending.current(pendingAction)
    setPendingAction(null)
  }, [firstView, pendingAction])
  // Waiting for the first view, or for every row when this view needs them: say what is being read.
  if (waiting && !shownOnce.current)
    return <div className="space-y-3">{firstView.loading}</div>
  return (
    <section
      ref={setSectionEl}
      aria-label="Browse ledger rows"
      // On the Transactions page a strip on the right holds the control panel's tab, so it never covers a control.
      className={`space-y-3 ${investigation && exportContext ? "pr-8" : ""}`}
    >
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
      {notesCsv && exportContext && !waiting && (
        <TransactionNotesCsv
          caseId={exportContext.caseId}
          rows={transactions}
          onClose={() => setNotesCsv(false)}
        />
      )}
      {!investigation && transactionToolbar}
      {!investigation && categoryBar}
      {!(investigation && exportContext) && (
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
      )}
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
      {!(investigation && exportContext) && judgementNote}
      {investigation && exportContext && !waiting && firstData && first.isFetching && (
        <p role="status" className="text-sm text-muted-foreground">
          Updating transactions for these filters…
        </p>
      )}
      {investigation && exportContext && (
        <>
          {!waiting && (
          <TransactionsOverview
            caseId={exportContext.caseId}
            show={sections}
            rows={shownAmounts}
            summary={firstData?.currencies}
            monthRows={sectionRows.months}
            tileRows={sectionRows.tiles}
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
          )}
          {!waiting && chipLine}
          {sections.accountTotals && !waiting && (
          <>
          <PaymentTotals
            rows={shownAmounts}
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
          </>
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
          {searchBar}
          <TransactionControlPanel
            open={controlsOpen}
            onOpenChange={setControlsOpen}
            activeCount={activeFilterCount}
            anchor={sectionEl}
          >
            {/* Collapsed, the panel stays mounted; in the first view its counts would cover one page only, so it
                holds nothing until every row is read (opening it reads them). */}
            {waiting ? (
              <p className="text-sm text-muted-foreground" role="status">
                Reading every payment for these controls…
              </p>
            ) : firstData ? null : (
            <>
            <ControlGroup title="Show on the page">
              {TRANSACTION_SECTIONS.map((section) => {
                const viewKey = "viewKey" in section ? section.viewKey : undefined
                return (
                  <SectionSwitch
                    key={section.key}
                    label={section.label}
                    hint={section.hint}
                    on={viewKey ? !!view[viewKey] : sections[section.key]}
                    onChange={(on) => {
                      setSection(section.key, on)
                      // Showing or hiding a section keeps the table on the page it is on.
                      if (viewKey) setView((previous) => ({ ...previous, [viewKey]: on }))
                    }}
                  />
                )
              })}
            </ControlGroup>
            <ControlGroup title="Accounts and dates">
              {!independentFilters && !exportContext.profile && (
                <WorkspaceScope caseId={exportContext.caseId} datesOnly />
              )}
            <TransactionAccountFilters
              caseId={exportContext.caseId}
              selection={accountScope}
              onChange={(selection) => {
                const next = { ...accountScope, ...selection }
                retainPaymentTableView(exportContext.caseId, accountScope, next)
                applyAccountScope(next)
              }}
            />
            </ControlGroup>
            {categoryBar && <ControlGroup title="Categories">{categoryBar}</ControlGroup>}
            <ControlGroup title="Payments">
              <div className="flex flex-wrap items-end gap-3">
                {activityControl}
                {internalNote}
              </div>
              {filterFields}
            </ControlGroup>
            <ControlGroup title="Display">
              <div className="flex flex-wrap items-center gap-2">
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
              </div>
            </ControlGroup>
            </>
            )}
          </TransactionControlPanel>
          {sort.startsWith("amount") && mixedCurrencies && (
            <p className="text-xs text-muted-foreground">
              Sorted by amount size across currencies. Money in or out does not
              change this order; currencies are not converted.
            </p>
          )}
          {!waiting && (
          <TransactionAnalysisPanels
            hideControls
            rows={sectionRows.analysis}
            filters={view}
            panels={view}
            onChange={changeView}
          />
          )}
          <div className="space-y-3">
            {selection.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span>{selection.length} payments selected</span>
                <Button variant="ghost" onClick={() => setSelection([])}>
                  Clear selection
                </Button>
              </div>
            )}
            {selection.length > 0 && (
              <>
                <div className="flex flex-wrap items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 p-3">
                  <Button variant="outline" onClick={() => setCompare(true)}>
                    Compare payments
                  </Button>
                  {exportContext && (() => {
                    // The chosen payments as one group for a theory, with the ledger filter they were chosen under.
                    const labels = new Map(transactions.map((row) => [row.key, `${row.ordering_date} · ${row.description ?? row.txn_number}`]))
                    const filter = Object.fromEntries(Object.entries({
                      search, currency, minimum, maximum, direction, proof, sourceFilename,
                      categories: categories.length ? categories : undefined,
                      ...exportContext.params,
                    }).filter(([, v]) => v !== undefined && v !== null && v !== "" && !(Array.isArray(v) && !v.length)))
                    const said = Object.entries(filter).map(([k, v]) => `${k} ${Array.isArray(v) ? v.join(", ") : String(v)}`).join("; ")
                    return selection.length === 1 ? (
                      <AddToTheory caseId={exportContext.caseId} surface="financial" size="default" items={[{ target_type: "financial_transaction", target_id: selection[0], target_label: labels.get(selection[0]) }]} />
                    ) : (
                      <AddToTheory
                        caseId={exportContext.caseId}
                        surface="financial"
                        size="default"
                        group={{
                          group_type: "financial_selection",
                          members: selection.map((id) => ({ type: "financial_transaction" as const, id, label: labels.get(id) })),
                          how: { filter, picked: selection.length },
                          words: `${selection.length} payments chosen in the ledger${said ? ` (${said})` : ""}`.slice(0, 480),
                        }}
                      />
                    )
                  })()}
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
                  {canEdit && (
                    <Button
                      variant="outline"
                      onClick={() => setAddToFinding(true)}
                    >
                      Add to existing finding
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
                {addToFinding && (
                  <AddPaymentsToFinding
                    caseId={exportContext.caseId}
                    ids={selection}
                    onClose={() => setAddToFinding(false)}
                  />
                )}
                <Disclosure className="text-sm" label="Selected amounts and saved selections">
                  <div className="space-y-3 pt-2">
                    {/* While every row is read nothing here is counted: the selection's rows are not in yet. */}
                    {waiting ? (
                      <p className="text-muted-foreground" role="status">
                        The selected amounts are added up once every payment is read.
                      </p>
                    ) : (
                      <PaymentTotals
                        rows={selectedHere}
                        label="Selected payments in this account/date range"
                      />
                    )}
                    <SavePaymentSelection
                      onReviewSelection={() => setReviewSelection(true)}
                      caseId={exportContext.caseId}
                      ids={selection}
                    />
                  </div>
                </Disclosure>
                {!waiting && selection.length >
                  rows.filter((row) => selectedIds.has(row.key)).length && (
                  <p className="text-sm rounded border p-2">
                    {selection.length -
                      rows.filter((row) => selectedIds.has(row.key))
                        .length}{" "}
                    selected payments are hidden by the current filters. Compare
                    or review the selection to see every attached payment.
                  </p>
                )}
                {!waiting && selection.length > selectedHere.length && (
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
      {/* An action that needs every row (CSV, select all, naming one by one) runs once they are read. */}
      {waiting ? firstView?.loading : firstData && pendingAction && firstView?.status}
      {investigation && exportContext && !waiting && (unnamedCount > 0 || view.unnamedOnly) && (
        <div
          className="flex flex-wrap items-center gap-2 rounded border border-status-warning border-l-4 bg-status-warning-soft px-3 py-2 text-sm"
          role="group"
          aria-label="Payments without a name"
        >
          <CheckTag />
          <span role="status">
            <strong>{unnamedCount.toLocaleString()}</strong>{" "}
            {unnamedCount === 1 ? "payment" : "payments"} in view with
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
          {unnamedCount > 0 && (
            <Button
              size="sm"
              onClick={() => (firstData ? needAll({ kind: "nameFirst" }) : nameFirst())}
            >
              {canEdit ? "Name them one by one" : "See their statement lines one by one"}
            </Button>
          )}
        </div>
      )}
      {investigation && exportContext && !waiting && (unconfirmedCount > 0 || view.unconfirmedOnly || readingsShown) && (
        <div
          className="flex flex-wrap items-center gap-2 rounded border border-status-warning border-l-4 bg-status-warning-soft px-3 py-2 text-sm"
          role="group"
          aria-label="Names read by Claude, not confirmed"
        >
          <CheckTag />
          <span role="status">
            {unconfirmedCount > 0
              ? unconfirmedNamesLabel(unconfirmedCount, firstData ? null : unconfirmedRows)
              : "Every name in view that Claude read is now confirmed or corrected by a person"}
          </span>
          {(unconfirmedCount > 0 || view.unconfirmedOnly) && (
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
          )}
          {canEdit && unconfirmedCount > 0 && (
            <Button
              size="sm"
              onClick={() => (firstData ? needAll({ kind: "confirmFirst" }) : confirmFirst())}
            >
              Confirm them one by one
            </Button>
          )}
          {canEdit && selection.length > 0 && (
            <BulkConfirmReadings
              caseId={exportContext.caseId}
              rows={selectedHere}
              notLoaded={selection.length - selectedHere.length}
            />
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
      <ReadingCheckContext.Provider value={readingCheck}>
      <RowJudgements.Provider value={tintedContext}>
      {waiting ? null : !total ? (
        <p>
          No payments match these filters. Clear the filters or choose another
          account/date range.
        </p>
      ) : investigation && exportContext && !tableView ? (
        <PaymentCardList
          caseId={exportContext?.caseId}
          findings={findings.data}
          categoryColors={categoryColors}
          rows={pageRows}
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
                  if (firstData) return needAll({ kind: "walk", key: row.key })
                  startWalk(row.key)
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
          caseId={exportContext?.caseId}
          columns={tableColumns}
          statementNames={tableStatementNames}
          findings={findings.data}
          categoryColors={categoryColors}
          rows={pageRows}
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
                  if (firstData) return needAll({ kind: "walk", key: row.key })
                  startWalk(row.key)
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
          transactions={pageRows}
          {...actions}
        />
      )}
      </RowJudgements.Provider>
      </ReadingCheckContext.Provider>
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
            onClose={closeNaming}
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
        {!waiting && total > pageSize && (
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
              {Math.min((index + 1) * pageSize, total)} of {total}{" "}
              matching rows
            </span>
            <Button
              variant="outline"
              disabled={(index + 1) * pageSize >= total}
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
