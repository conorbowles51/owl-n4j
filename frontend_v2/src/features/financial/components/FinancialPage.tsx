import { OverviewStatementCoverage } from "./OverviewStatementCoverage"
import { Disclosure } from "./Disclosure"
import { BatchSavedAccounts } from "./BatchSavedAccounts"
import { ActiveCategoryNotice } from "./PaymentCategoryFilter"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useStatementWorkspace } from "../stores/statement-workspace"
import "../financial-workspace.css"
import { useUIStore } from "@/stores/ui.store"
import {
  resetPaymentTableView,
  showAllImportedPayments,
} from "../lib/payment-table-draft"
import { useFinancialDraft } from "../stores/financial-drafts"
import { useOtherRecordsView } from "../hooks/use-other-records-view"
import { useFinancialViewNavigation } from "../hooks/use-financial-view-navigation"
import { useEvidenceReportDownload } from "../hooks/use-evidence-report-download"
import { useFinancialAccess } from "../hooks/use-financial-access"
import {
  FinancialAccessProvider,
  FinancialAccessNotice,
} from "./FinancialAccessProvider"
import { useCase } from "@/features/cases/hooks/use-cases"
import {
  FinancialNavigation,
  FinancialResetSlotProvider,
  RetainedFinancialTab,
} from "./FinancialNavigation"
import { FinancialFindings } from "./FinancialFindings"
import { FinancialAccounts } from "./FinancialAccounts"
import { StatementRegisterChecks } from "./StatementRegisterChecks"
import { ReferencedAccounts } from "./ReferencedAccounts"
import { useInvestigationScope } from "../stores/investigation-scope"
import {
  StatementImportPanel,
  type StatementImportReceipt,
} from "./StatementImportPanel"
import { FinancialPatternReview } from "./FinancialPatternReview"
import { FinancialGuide } from "./FinancialGuide"
import { FinancialCaseTimeline } from "./FinancialCaseTimeline"
import { LedgerPostingGraph } from "./LedgerPostingGraph"
import { LedgerTransfersWorkbench } from "./LedgerTransfersWorkbench"
import { LedgerTracingWorkbench } from "./LedgerTracingWorkbench"
import { InvestigatorPeople } from "./InvestigatorPeople"
import { AccountTypeReview } from "./AccountTypeReview"
import { InvestigatorOverview } from "./InvestigatorOverview"
import { useFinancialViewSpeed } from "../lib/page-speed"
import { InvestigatorFollowMoney } from "./InvestigatorFollowMoney"
import { InvestigatorTrends } from "./InvestigatorTrends"
import { StatementRegister } from "./StatementRegister"
import { ReviewQueuePanel } from "./ReviewQueuePanel"
import { LedgerSourceDialog } from "./LedgerSourceDialog"
import { JudgementCallsLabel, JudgementCallsPanel } from "./JudgementCallsPanel"
import { JUDGEMENT_KEYS } from "../lib/judgements"
import { CaseReviewStatus } from "./CaseReviewStatus"
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { useParams, useSearchParams } from "react-router-dom"
import { BarChart3, DollarSign, Users } from "lucide-react"
import { Button } from "@/components/ui/button"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { ErrorBoundary } from "@/components/ui/error-boundary"
import { Tabs } from "@/components/ui/tabs"
import {
  useFinancialStore,
  type FinancialMainView,
} from "../stores/financial.store"
import {
  useTransactions,
  useFinancialEntities,
  useFinancialCategories,
  useCategorize,
  useBatchCategorize,
  useCreateCategory,
  useUpdateDetails,
  useUpdateAmount,
  useSetFromTo,
  useBatchSetFromTo,
  useBulkCorrect,
  useLinkSubTransaction,
  useUnlinkSubTransaction,
} from "../hooks/use-financial-data"
import { useFilteredTransactions } from "../hooks/use-filtered-transactions"
import { useElapsedSeconds } from "../lib/request-wait"
import { FinancialToolbar } from "./FinancialToolbar"
import { FinancialFilterPanel } from "./FinancialFilterPanel"
import { FinancialSummaryCards } from "./FinancialSummaryCards"
import { TransactionTable } from "./TransactionTable"
import { FinancialCharts } from "./FinancialCharts"
import { DuplicateCandidatesPanel } from "./DuplicateCandidatesPanel"
import { StatementChecksPanel } from "./StatementChecksPanel"
import { StatementCoveragePanel } from "./StatementCoveragePanel"
import { PdfCandidatesPanel } from "./PdfCandidatesPanel"
import { ProofStandingPanel } from "./ProofStandingPanel"
import { CorrectableLedger } from "./CorrectableLedger"
import { RecordsModeSwitch } from "./RecordsModeSwitch"
import { InfoTip } from "./InfoTip"
import { RowAdjudicationDialog } from "./RowAdjudicationDialog"
import { IngestionRunNotice } from "./IngestionRunNotice"
import { IngestionRunsPanel } from "./IngestionRunsPanel"
import { DecisionsPanel } from "./DecisionsPanel"
import { BulkCategorizeDialog } from "./BulkCategorizeDialog"
import { CategoryManagementDialog } from "./CategoryManagementDialog"
import { SubTransactionDialog } from "./SubTransactionDialog"
import { AmountEditDialog } from "./AmountEditDialog"
import { EntityEditDialog } from "./EntityEditDialog"
import { BulkImportDialog } from "./BulkImportDialog"
import { TablePagination } from "@/features/table/components/TablePagination"
import type {
  FinancialDatasetMode,
  LedgerTransaction,
  Transaction,
} from "../api"

// The views that show the statement payments / other records switch (the access notice sits on its line).
const RECORDS_SWITCH_VIEWS = new Set<string>(["transactions", "counterparties", "trends"])

export function FinancialPage() {
  const { id: caseId } = useParams()
  return (
    <FinancialAccessProvider caseId={caseId}>
      <FinancialPageContent />
    </FinancialAccessProvider>
  )
}

function FinancialPageContent() {
  const { id: caseId } = useParams()
  const { canEdit } = useFinancialAccess()
  const store = useFinancialStore()
  useFinancialViewNavigation(caseId)
  useOtherRecordsView(caseId)
  const currentCase = useCase(caseId)
  const {
    download: downloadEvidenceReport,
    busy: evidenceReportBusy,
    error: evidenceReportError,
  } = useEvidenceReportDownload(caseId)
  const [importReceipt, setImportReceipt] =
    useState<StatementImportReceipt | null>(null)
  const [, applyInvestigationScope] = useInvestigationScope(caseId)
  const openAllPayments = () => {
    if (caseId) showAllImportedPayments(caseId)
    setImportReceipt(null)
  }
  const navigateFinancial = (view: FinancialMainView) => {
    if (view === "transactions") store.setMode("transactions")
    store.setMainView(view)
  }
  const [params, setParams] = useSearchParams()
  type StatementSection = "queue" | "files" | "accounts" | "batches" | "remove" | "judgements"
  const [statementSection, setStatementSection] = useState<{
    caseId: string | undefined
    section: StatementSection
  }>({ caseId, section: "queue" }) // The review queue opens first: statement work is done there.
  const section =
    params.get("queue") === "1"
      ? "queue"
      : params.get("judgements") === "1"
      ? "judgements"
      : params.get("files") === "1"
      ? "files"
      : params.get("accounts") === "1"
        ? "accounts"
      : params.get("batch")
        ? "batches"
        : statementSection.caseId === caseId
          ? statementSection.section
          : "queue"
  const reviewingAccounts = section === "accounts"
  useFinancialViewSpeed(
    caseId,
    store.mainView === "statements" ? `financial/statements/${section}` : `financial/${store.mainView}`
  )
  const statementScroll = useRef<HTMLDivElement>(null)
  const accountsDestination = useRef<HTMLDivElement>(null)

  const owner = useAuthStore(
    (state) => state.user?.id || state.user?.username || "anonymous"
  )
  const workspaceScope = `${owner}:${caseId}`
  const workspaceReview = useStatementWorkspace(
    (state) => state.selections[workspaceScope]
  )
  const routedReviewFile = params.get("reviewFile")
  const linkedPayment = params.get("payment")
  const returnBatch = params.get("returnBatch")
  const savedBatchAccounts = reviewingAccounts && params.get("savedBatch") === "1" && !!returnBatch
  useEffect(() => {
    if (reviewingAccounts && returnBatch) accountsDestination.current?.focus()
  }, [reviewingAccounts, returnBatch])
  const explicitFiles = params.get("files") === "1"
  const appliedFileRoute = useRef("")
  const changingStatementRoute = useRef(false)
  useEffect(() => {
    const route = JSON.stringify([workspaceScope, section, explicitFiles, routedReviewFile])
    const workspace = useStatementWorkspace.getState()
    if (route !== appliedFileRoute.current) {
      appliedFileRoute.current = route
      changingStatementRoute.current = false
      if (section === "files" && routedReviewFile)
        workspace.select(workspaceScope, routedReviewFile)
      else if (section === "files" && explicitFiles)
        workspace.setOpen(workspaceScope, false)
      return
    }
    if (changingStatementRoute.current || section !== "files" || !explicitFiles) return
    // Keep the route accurate when the review's file selector or close action
    // changes the workspace, so refresh and browser Back restore that choice.
    const selected = workspace.selections[workspaceScope]
    const fileId = selected?.open ? selected.fileId : null
    if (fileId === routedReviewFile) return
    setParams((current) => {
      const next = new URLSearchParams(current)
      if (fileId) next.set("reviewFile", fileId)
      else next.delete("reviewFile")
      return next
    }, { replace: true })
  }, [section, explicitFiles, routedReviewFile, workspaceScope, workspaceReview?.open, workspaceReview?.fileId, setParams])
  const showStatementSection = (next: StatementSection) => {
    changingStatementRoute.current = true
    setStatementSection({ caseId, section: next })
    if (next === "files" || next === "remove")
      useStatementWorkspace.getState().setOpen(workspaceScope, false)
    setParams((current) => {
      const updated = new URLSearchParams(current)
      for (const key of [
        "batch", "batchItem", "batchRow", "batchCheck", "files", "accounts", "savedBatch", "savedOperation",
        "reviewFile", "returnBatch", "returnBatchCheck", "queue", "queueItem", "queueList", "queueFiles", "judgements",
        ...JUDGEMENT_KEYS,
      ])
        updated.delete(key)
      if (next === "queue") updated.set("queue", "1")
      if (next === "judgements") updated.set("judgements", "1")
      return updated
    })
  }
  const openBatchFromQueue = (batchId: string, check?: string) => {
    changingStatementRoute.current = true
    setStatementSection({ caseId, section: "batches" })
    setParams((current) => {
      const updated = new URLSearchParams(current)
      for (const key of ["queue", "queueItem", "queueList", "queueFiles", "files", "batchItem", "batchRow"])
        updated.delete(key)
      updated.set("view", "statements")
      updated.set("batch", batchId)
      if (check) updated.set("batchCheck", check)
      else updated.delete("batchCheck")
      return updated
    })
  }
  const reviewStatement = (fileId: string) => {
    showStatementSection("files")
    useStatementWorkspace.getState().select(workspaceScope, fileId)
    store.setMainView("statements")
  }
  const returnToBatch = () => {
    if (!returnBatch) return
    changingStatementRoute.current = true
    setStatementSection({ caseId, section: "batches" })
    setParams((current) => {
      const next = new URLSearchParams(current)
      const check = next.get("returnBatchCheck")
      for (const key of [
        "files", "accounts", "savedBatch", "savedOperation", "reviewFile", "returnBatch", "returnBatchCheck",
        "batchItem", "batchRow", "batchCheck",
      ]) next.delete(key)
      next.set("view", "statements")
      next.set("batch", returnBatch)
      if (check) next.set("batchCheck", check)
      return next
    })
  }
  useEffect(() => {
    statementScroll.current?.scrollTo?.({ top: 0 })
  }, [section, workspaceReview?.open, workspaceReview?.fileId])
  useEffect(() => {
    const panel = useUIStore.getState()
    if (store.mainView !== "statements" && panel.graphPanelTab === "detail")
      panel.setGraphPanelCollapsed(true)
  }, [caseId, store.mainView])
  // The graph's records (d5b330d1: 33.6 MB, 6-14 s of server time) are shown only by the graph sections of
  // Transactions, Counterparties and Trends in "Other financial records" mode, so they are read only there.
  const graphShown =
    RECORDS_SWITCH_VIEWS.has(store.mainView) && store.mode !== "transactions"
  const {
    data: transactionsResponse,
    isLoading: graphFetching,
    isError: transactionsFailed,
    error: transactionsError,
  } = useTransactions(caseId, {
    mode: store.mode,
  }, { enabled: graphShown })
  // Until its answer arrives a graph section says it is loading: never an empty case or a count of 0.
  const isLoading = graphFetching || (!transactionsResponse && !transactionsFailed)
  const loadingSeconds = useElapsedSeconds(isLoading && graphShown)
  const { data: categories = [] } = useFinancialCategories(caseId, store.mode)
  const { data: caseEntities = [] } = useFinancialEntities(caseId)
  const transactions = transactionsResponse?.transactions ?? []
  const usesLegacyFinancialModel =
    transactionsResponse?.uses_legacy_financial_model ?? false
  const isTransactionsMode = store.mode === "transactions"
  const [partyView, setPartyView] = useFinancialDraft<{
    senders: string[]
    beneficiaries: string[]
  }>(caseId || "", "other-record-parties", { senders: [], beneficiaries: [] })
  const selectedSenders = useMemo(
    () => new Set(partyView.senders),
    [partyView.senders]
  )
  const selectedBeneficiaries = useMemo(
    () => new Set(partyView.beneficiaries),
    [partyView.beneficiaries]
  )
  const setSelectedSenders = useCallback(
    (values: Set<string>) =>
      setPartyView((current) => ({ ...current, senders: [...values] })),
    [setPartyView]
  )
  const setSelectedBeneficiaries = useCallback(
    (values: Set<string>) =>
      setPartyView((current) => ({ ...current, beneficiaries: [...values] })),
    [setPartyView]
  )

  const categorize = useCategorize(caseId!)
  const batchCategorize = useBatchCategorize(caseId!)
  const createCategory = useCreateCategory(caseId!)
  const updateDetails = useUpdateDetails(caseId!)
  const updateAmount = useUpdateAmount(caseId!)
  const setFromTo = useSetFromTo(caseId!)
  const batchSetFromTo = useBatchSetFromTo(caseId!)
  const bulkCorrect = useBulkCorrect(caseId!)
  const linkSub = useLinkSubTransaction(caseId!)
  const unlinkSub = useUnlinkSubTransaction(caseId!)

  const {
    filteredTransactions,
    pageTransactions,
    filteredCount,
    pageCount,
    categoryCounts,
    currentPage: visibleRecordsPage,
  } = useFilteredTransactions(transactions, {
    searchQuery: store.searchQuery,
    selectedCategories: store.selectedCategories,
    startDate: store.startDate,
    endDate: store.endDate,
    entityFilter: store.entityFilter,
    selectedFromEntities: selectedSenders,
    selectedToEntities: selectedBeneficiaries,
    minAmount: store.minAmount,
    maxAmount: store.maxAmount,
    sortColumns: store.sortColumns,
    pageSize: store.pageSize,
    currentPage: store.currentPage,
  })

  const [bulkCategorizeOpen, setBulkCategorizeOpen] = useState(false)
  const [categoryMgmtOpen, setCategoryMgmtOpen] = useState(false)
  const [subTxDialogOpen, setSubTxDialogOpen] = useState(false)
  const [subTxParent, setSubTxParent] = useState<Transaction | null>(null)
  const [amountEditOpen, setAmountEditOpen] = useState(false)
  const [amountEditTx, setAmountEditTx] = useState<Transaction | null>(null)
  const [entityEditOpen, setEntityEditOpen] = useState(false)
  const [entityEditField, setEntityEditField] = useState<"from" | "to">("from")
  const [entityEditKeys, setEntityEditKeys] = useState<string[]>([])
  const [bulkImportOpen, setBulkImportOpen] = useState(false)

  /**
   * The row a person asked to change, held by the page rather than by the panel
   * the row was in.
   *
   * A change that succeeds invalidates the ledger reads, so the row leaves the
   * list it was clicked in: setting a row aside drops it out of the ledger, and
   * letting one back in drops it out of the held-back list. Both panels return
   * an empty state before rendering anything below it, so a dialog owned by a
   * panel would be unmounted at the moment the change landed -- and the answer
   * to the change is said in that one response and nowhere else. Held here, the
   * dialog outlives the row's disappearance and closes only when the person
   * closes it.
   */
  const [adjudicationRow, setAdjudicationRow] =
    useState<LedgerTransaction | null>(null)

  const handleCategorize = useCallback(
    (nodeKey: string, category: string) => {
      return categorize.mutateAsync({ nodeKey, category })
    },
    [categorize]
  )

  const handleBulkCategorize = useCallback(
    (category: string) => {
      batchCategorize.mutate(
        { nodeKeys: Array.from(store.checkedKeys), category },
        {
          onSuccess: () => {
            setBulkCategorizeOpen(false)
            store.clearChecked()
          },
        }
      )
    },
    [batchCategorize, store]
  )

  const handleAmountClick = useCallback((tx: Transaction) => {
    setAmountEditTx(tx)
    setAmountEditOpen(true)
  }, [])

  const handleAmountSave = useCallback(
    async (newAmount: number, correctionReason: string) => {
      if (!amountEditTx)
        throw new Error("Reopen the payment to correct its amount.")
      if (amountEditTx.amount === null && amountEditTx.raw_amount === undefined)
        throw new Error(
          "The original amount text is missing. Reload this record before correcting it."
        )
      return updateAmount.mutateAsync({
        nodeKey: amountEditTx.key,
        newAmount,
        correctionReason,
        expectedAmount: amountEditTx.amount ?? undefined,
        expectedRawAmount:
          amountEditTx.amount === null ? amountEditTx.raw_amount : undefined,
      })
    },
    [amountEditTx, updateAmount]
  )

  const handleEntityEdit = useCallback(
    (tx: Transaction, field: "from" | "to") => {
      setEntityEditField(field)
      setEntityEditKeys([tx.key])
      setEntityEditOpen(true)
    },
    []
  )

  const handleEntitySave = useCallback(
    (entity: { key?: string; name?: string }) => {
      const params =
        entityEditField === "from"
          ? { fromKey: entity.key, fromName: entity.name }
          : { toKey: entity.key, toName: entity.name }

      if (entityEditKeys.length === 1) {
        setFromTo.mutate(
          { nodeKey: entityEditKeys[0], ...params },
          { onSuccess: () => setEntityEditOpen(false) }
        )
      } else {
        batchSetFromTo.mutate(
          { nodeKeys: entityEditKeys, ...params },
          {
            onSuccess: () => {
              setEntityEditOpen(false)
              store.clearChecked()
            },
          }
        )
      }
    },
    [entityEditField, entityEditKeys, setFromTo, batchSetFromTo, store]
  )

  const handleSaveDetails = useCallback(
    (
      nodeKey: string,
      fields: { purpose?: string; counterpartyDetails?: string; notes?: string }
    ) => {
      updateDetails.mutate({ nodeKey, ...fields })
    },
    [updateDetails]
  )

  const handleGroupSubTransactions = useCallback((tx: Transaction) => {
    setSubTxParent(tx)
    setSubTxDialogOpen(true)
  }, [])

  const handleRemoveFromGroup = useCallback(
    (tx: Transaction) => {
      if (tx.parent_transaction_key) {
        unlinkSub.mutate({ childKey: tx.key })
      }
    },
    [unlinkSub]
  )

  const handleCreateCategory = useCallback(
    (name: string, color: string) => {
      return createCategory.mutateAsync({ name, color })
    },
    [createCategory]
  )

  const handleBulkImport = useCallback(
    async (
      corrections: {
        node_key: string
        new_amount: number
        correction_reason: string
        expected_amount?: number
        expected_raw_amount?: string | null
      }[]
    ) => {
      return bulkCorrect.mutateAsync(corrections)
    },
    [bulkCorrect]
  )

  const handleModeChange = useCallback(
    (mode: FinancialDatasetMode) => {
      if (mode === store.mode) return
      store.setMode(mode)
      setSelectedSenders(new Set())
      setSelectedBeneficiaries(new Set())
    },
    [store, setSelectedSenders, setSelectedBeneficiaries]
  )

  const handleExportPdf = useCallback(() => {
    if (!caseId) return

    const params = new URLSearchParams({
      case_id: caseId,
      mode: store.mode,
      include_entity_notes: "true",
      case_name: currentCase.data?.title || "Case",
    })

    if (store.selectedCategories.size > 0) {
      for (const category of store.selectedCategories)
        params.append("category_names", category)
    }
    if (store.startDate) params.set("start_date", store.startDate)
    if (store.endDate) params.set("end_date", store.endDate)
    if (store.entityFilter?.key) {
      params.set("entity_key", store.entityFilter.key)
      params.set("entity_name", store.entityFilter.name)
    }
    if (store.searchQuery.trim()) {
      params.set("search", store.searchQuery.trim())
    }
    if (selectedSenders.size > 0) {
      for (const sender of selectedSenders)
        params.append("sender_values", sender)
    }
    if (selectedBeneficiaries.size > 0) {
      for (const beneficiary of selectedBeneficiaries)
        params.append("beneficiary_values", beneficiary)
    }

    if (store.minAmount.trim()) params.set("min_amount", store.minAmount.trim())
    if (store.maxAmount.trim()) params.set("max_amount", store.maxAmount.trim())
    void downloadEvidenceReport(params)
  }, [
    caseId,
    currentCase.data?.title,
    downloadEvidenceReport,
    store.minAmount,
    store.maxAmount,
    store.mode,
    store.selectedCategories,
    store.startDate,
    store.endDate,
    store.entityFilter,
    store.searchQuery,
    selectedSenders,
    selectedBeneficiaries,
  ])

  const subTransactions = subTxParent
    ? transactions.filter((t) => t.parent_transaction_key === subTxParent.key)
    : []

  /**
   * Four pieces of chrome, all of which describe the Neo4j graph and only the
   * graph. The toolbar counts graph rows against graph rows, the banner is
   * about the graph dataset model, the filter panel offers graph categories
   * and graph entities, and the summary cards total graph transactions.
   *
   * They used to sit above the tab strip, where they would now also sit above
   * the ledger table. A row of counts and totals that does not describe the
   * table underneath it is the same failure the standing rule about corrected
   * values exists to prevent: a number on screen that looks like it is about
   * what you are reading and is not. So they render inside the graph tabs and
   * nowhere else, which also leaves each of the four describing exactly one
   * store, with none of them having to know which store is on screen.
   *
   * Reusing one element in three places creates three instances in the tree,
   * and Radix mounts only the active tab's content, so exactly one is ever
   * live.
   */
  const graphChrome = (
    <>
      <FinancialToolbar
        mode={store.mode}
        filteredCount={filteredCount}
        totalCount={transactions.length}
        onOpenBulkImport={() => setBulkImportOpen(true)}
        onOpenCategoryManagement={() => setCategoryMgmtOpen(true)}
        onExportPdf={handleExportPdf}
        isExporting={evidenceReportBusy}
      />

      {evidenceReportError && (
        <p role="alert" className="p-3 text-sm text-destructive">
          {evidenceReportError}
        </p>
      )}
      {usesLegacyFinancialModel && (
        <div className="border-b border-yellow-500/25 bg-yellow-500/10 px-4 py-2 text-xs text-yellow-800 dark:text-yellow-200">
          Some older financial records may lack original file or page details.
          Open Evidence to check the source document.
        </div>
      )}

      <FinancialFilterPanel
        categories={categories}
        categoryCounts={categoryCounts}
        allEntities={caseEntities}
      />

      <FinancialSummaryCards
        transactions={filteredTransactions}
        mode={store.mode}
      />
    </>
  )

  /**
   * The in-flight and no-rows states belong to the graph query, and they used
   * to return from the whole page — which put them above the tab strip and
   * meant the tab strip did not exist until the graph had rows.
   *
   * A case that has just had a bank file sent to the ledger is in exactly that
   * position: ledger rows, no graph. The old arrangement hid the ledger tab
   * precisely when the ledger had something to show. Both states guard the
   * graph tabs' own content now, and the ledger tab is reachable regardless of
   * what the graph query returned. `LedgerPanel` owns its own no-case,
   * in-flight, failed and empty states, so nothing here has to stand in for
   * them.
   */
  const graphTab = (content: ReactNode) => {
    if (isLoading) {
      return (
        <div
          className="flex flex-1 flex-col items-center justify-center gap-3"
          data-testid="records-loading"
        >
          <LoadingSpinner size="lg" />
          <p role="status" className="text-sm text-muted-foreground">
            Loading other financial records…
            {loadingSeconds > 0 && ` ${loadingSeconds} s`}
          </p>
        </div>
      )
    }

    // A failed read is never shown as an empty case.
    if (transactionsFailed) {
      return (
        <div
          className="flex flex-1 items-center justify-center p-4 text-sm text-destructive"
          role="alert"
          data-testid="records-error"
        >
          These records could not be loaded. Refresh this page to try again.
          {transactionsError instanceof Error
            ? ` ${transactionsError.message}`
            : ""}
        </div>
      )
    }

    if (!transactions.length) {
      return (
        <div className="flex flex-1 items-center justify-center p-4">
          <EmptyState
            icon={DollarSign}
            title={
              isTransactionsMode
                ? "No documentary transactions"
                : "No other financial records"
            }
            description={
              isTransactionsMode
                ? "Process evidence with documentary financial records to populate this view"
                : "Amounts read from other evidence appear here after processing in Evidence. Use Statements to upload bank statements."
            }
          />
        </div>
      )
    }

    return (
      <>
        {graphChrome}
        {content}
      </>
    )
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex shrink-0 items-center gap-3 bg-[#0b0c0f] px-4 pt-2.5 text-[#f7f7f8]">
        <span
          aria-hidden="true"
          className="inline-flex items-center gap-2 text-[17px] font-bold"
          style={{ fontFamily: "'Space Grotesk', ui-sans-serif, system-ui, sans-serif" }}
        >
          <span className="size-2 rounded-full bg-[#e33b4c] shadow-[0_0_0_5px_rgba(227,59,76,.15)]" />
          Loupe
        </span>
        <p
          className="min-w-0 flex-1 truncate text-sm font-semibold"
          title={
            currentCase.data && currentCase.data.id === caseId
              ? currentCase.data.title
              : caseId
          }
        >
          Financial ·{" "}
          {currentCase.data && currentCase.data.id === caseId
            ? currentCase.data.title
            : currentCase.isPending
              ? "Loading case…"
              : (caseId ?? "Choose a case")}
        </p>
        <FinancialGuide />
      </div>
      {/* "Reset view" sits at the right end of the tab bar, not in a band of its own. */}
      <FinancialResetSlotProvider>
      <Tabs
        key={`financial-tabs:${caseId}`}
        value={store.mainView}
        onValueChange={(value) => navigateFinancial(value as FinancialMainView)}
        className="flex min-h-0 flex-1 flex-col"
      >
        <FinancialNavigation
          value={store.mainView}
          onChange={navigateFinancial}
        />
        {/* Views with the records switch show the access notice on its line. */}
        {!RECORDS_SWITCH_VIEWS.has(store.mainView) && <FinancialAccessNotice />}
        {/* Categories are chosen and managed under Transactions (Alex: not at
            the top of every view). A category chosen there still narrows the
            analysis views, so they say so instead of filtering silently. */}
        {caseId &&
          store.mode === "transactions" &&
          [
            "overview",
            "counterparties",
            "follow-money",
            "trends",
            "posting-graph",
          ].includes(store.mainView) && (
            <ActiveCategoryNotice
              caseId={caseId}
              onChange={() => navigateFinancial("transactions")}
            />
          )}

        <RetainedFinancialTab
          value="overview"
          active={store.mainView === "overview"}
          className="min-h-0 flex-1 overflow-auto"
        >
          <ErrorBoundary level="section">
            {caseId && <InvestigatorOverview caseId={caseId} active={store.mainView === "overview"} />}
          </ErrorBoundary>
        </RetainedFinancialTab>
        <RetainedFinancialTab
          value="follow-money"
          active={store.mainView === "follow-money"}
          className="min-h-0 flex-1 overflow-auto"
        >
          <ErrorBoundary level="section">
            {caseId && <InvestigatorFollowMoney caseId={caseId} />}
          </ErrorBoundary>
        </RetainedFinancialTab>
        {/*
          The ledger tab reads Postgres and shares nothing with the three graph
          tabs: not the query, not the filters, not the counts. It deliberately
          takes none of the graph chrome and is not gated on the graph query,
          so a case with ledger rows and no graph opens here and shows them.
        */}
        <RetainedFinancialTab
          value="ledger"
          className="flex min-h-0 flex-1 flex-col"
          active={store.mainView === "ledger"}
        >
          <div className="min-h-0 flex-1 space-y-3 overflow-auto p-4">
            {/*
              A sibling of the panel and never a child of it. `LedgerPanel`
              returns early for no case, for a read in flight, for a failed
              read and for zero rows, so a notice nested inside it would
              disappear exactly when the ledger is empty -- which is the
              moment a broken attempt to load it is the explanation. This
              stays silent unless an attempt did not finish.
            */}
            <ErrorBoundary level="section">
              <IngestionRunNotice caseId={caseId} />
            </ErrorBoundary>
            <ErrorBoundary level="section">
              <ProofStandingPanel caseId={caseId} />
            </ErrorBoundary>
            <ErrorBoundary level="section">
              <DuplicateCandidatesPanel key={caseId} caseId={caseId} />
            </ErrorBoundary>
            <ErrorBoundary level="section">
              <PdfCandidatesPanel key={caseId} caseId={caseId} />
            </ErrorBoundary>
            <ErrorBoundary level="section">
              <CorrectableLedger
                key={caseId}
                caseId={caseId}
                onAdjudicate={setAdjudicationRow}
              />
            </ErrorBoundary>
          </div>
        </RetainedFinancialTab>

        {/*
          Reads Postgres like the ledger tab, takes no graph chrome and is not
          gated on the graph query, for the same reasons. The notice above the
          ledger is not repeated here: it explains why a ledger might be short,
          and nothing about a failed attempt to load evidence bears on whether
          the rows that did arrive are being held out of the totals.
        */}
        <RetainedFinancialTab
          value="statements"
          onReset={() => showStatementSection("files")}
          forceMount
          style={
            store.mainView !== "statements" ? { display: "none" } : undefined
          }
          className="flex min-h-0 flex-1 flex-col data-[state=inactive]:hidden"
          active={store.mainView === "statements"}
        >
          <div
            ref={statementScroll}
            className="min-h-0 flex-1 space-y-4 overflow-auto p-4"
          >
            <header className="space-y-1">
              <h2 className="text-2xl font-semibold">Statements & accounts</h2>
              <p className="text-sm text-muted-foreground">
                {canEdit
                  ? "Manage the PDFs behind your investigation: import payments, check account coverage, or remove a bad import and process it again."
                  : "Open the original statements and review their accounts and extracted payments."}
              </p>
            </header>
            {caseId && section !== "queue" && (
              <ErrorBoundary level="section">
                <CaseReviewStatus
                  caseId={caseId}
                  active={store.mainView === "statements"}
                  onOpen={() => showStatementSection("queue")}
                />
              </ErrorBoundary>
            )}
            <div
              className="sticky top-0 z-10 flex flex-wrap items-center gap-2 border-b bg-background py-2"
              role="group"
              aria-label="Statement workspace"
            >
              <Button
                variant={section === "queue" ? "primary" : "outline"}
                aria-pressed={section === "queue"}
                onClick={() => showStatementSection("queue")}
              >
                Review queue
              </Button>
              <Button
                variant={section === "judgements" ? "primary" : "outline"}
                aria-pressed={section === "judgements"}
                onClick={() => showStatementSection("judgements")}
              >
                {caseId ? <JudgementCallsLabel caseId={caseId} /> : "Judgement calls"}
              </Button>
              <Button
                variant={section === "files" ? "primary" : "outline"}
                aria-pressed={section === "files"}
                onClick={() => showStatementSection("files")}
              >
                Statement files
              </Button>
              <Button
                variant={reviewingAccounts ? "primary" : "outline"}
                aria-pressed={reviewingAccounts}
                onClick={() => showStatementSection("accounts")}
              >
                Review accounts
              </Button>
              <Button
                variant={section === "batches" ? "primary" : "outline"}
                aria-pressed={section === "batches"}
                onClick={() => showStatementSection("batches")}
              >
                Processing batches
              </Button>
              {canEdit && (
                <Button
                  variant={section === "remove" ? "primary" : "outline"}
                  aria-pressed={section === "remove"}
                  onClick={() => showStatementSection("remove")}
                >
                  Remove imports…
                </Button>
              )}
            </div>
            {reviewingAccounts && returnBatch && (
              <div role="status" tabIndex={-1} ref={accountsDestination} className="rounded border p-3 space-y-2">
                <p>Saved statements are recorded with their accounts, dates and balances below. No payment rows are created for statements without transactions.</p>
                <Button variant="outline" onClick={returnToBatch}>Back to processing batch</Button>
              </div>
            )}
            {savedBatchAccounts && caseId && (
              <BatchSavedAccounts
                key={`${caseId}:${returnBatch}:${params.get("savedOperation") || "all"}`}
                caseId={caseId}
                batchId={returnBatch!}
                operationId={params.get("savedOperation")}
                onShowAll={() => setParams((current) => { const next = new URLSearchParams(current); next.delete("savedBatch"); next.delete("savedOperation"); return next })}
              />
            )}
            <div hidden={!reviewingAccounts || savedBatchAccounts}>
              {reviewingAccounts && !savedBatchAccounts && caseId && <AccountOwnershipReview caseId={caseId} label="Review account ownership" />}
              {importReceipt &&
                importReceipt.case_id === caseId &&
                (importReceipt.record_count ??
                  importReceipt.transaction_count) === 0 && (
                  <p role="status" className="rounded border p-3 my-3">
                    {importReceipt.account_closed_on
                      ? `Recorded the account closure on ${importReceipt.account_closed_on} from `
                      : "Saved the account and statement balances from "}
                    {importReceipt.filename || "your statement"}. No payments
                    were added.
                  </p>
                )}
              {caseId && reviewingAccounts && !savedBatchAccounts && (
                <ErrorBoundary level="section">
                  <AccountTypeReview
                    caseId={caseId}
                    active={store.mainView === "statements"}
                  />
                </ErrorBoundary>
              )}
              {caseId && (
                <StatementRegisterChecks
                  caseId={caseId}
                  active={store.mainView === "statements" && reviewingAccounts && !savedBatchAccounts}
                  onReviewStatement={reviewStatement}
                  onOpenTransactions={(accountId, dates) => {
                    const scope = { accountId, ...dates }
                    resetPaymentTableView(caseId, scope)
                    applyInvestigationScope(scope)
                    store.setMode("transactions")
                    store.setMainView("transactions")
                  }}
                />
              )}
              <section
                className="rounded-lg border p-3 my-3 space-y-2"
                aria-label="Find an account by name, number or bank"
              >
                <h3 className="font-semibold">
                  Find an account by name, number or bank
                </h3>
                <ErrorBoundary level="section">
                  <FinancialAccounts
                    active={store.mainView === "statements" && reviewingAccounts && !savedBatchAccounts}
                    onReviewStatement={reviewStatement}
                    key={caseId}
                    caseId={caseId}
                    onOpenAccount={(accountId, dates) => {
                      const scope = { accountId, ...dates }
                      if (caseId) resetPaymentTableView(caseId, scope)
                      applyInvestigationScope(scope)
                      store.setMode("transactions")
                      store.setMainView("transactions")
                    }}
                  />
                </ErrorBoundary>
              </section>
            </div>
            {section === "queue" && caseId && (
              <ErrorBoundary level="section">
                <ReviewQueuePanel caseId={caseId} onOpenBatch={openBatchFromQueue} />
              </ErrorBoundary>
            )}
            {section === "judgements" && caseId && (
              <ErrorBoundary level="section">
                <JudgementCallsPanel caseId={caseId} />
              </ErrorBoundary>
            )}
            <div hidden={reviewingAccounts || section === "queue" || section === "judgements"}>
              {section === "files" && returnBatch && workspaceReview?.open && (
                <Button variant="outline" onClick={returnToBatch}>
                  Back to processing batch
                </Button>
              )}
              {caseId && (
                <StatementRegister
                  active={store.mainView === "statements" && !reviewingAccounts && section !== "queue" && section !== "judgements"}
                  mode={
                    section === "batches"
                      ? "batches"
                      : section === "remove"
                        ? "remove"
                        : "files"
                  }
                  onBackToFiles={() => showStatementSection("files")}
                  caseId={caseId}
                >
                  <StatementImportPanel
                    key={caseId}
                    caseId={caseId}
                    onImported={(result) => {
                      if (result) setImportReceipt(result)
                      const scope = { accountId: result?.account_id }
                      if (caseId) resetPaymentTableView(caseId, scope, result)
                      applyInvestigationScope(scope)
                      store.setMode("transactions")
                      if (
                        (result?.record_count ?? result?.transaction_count) ===
                        0
                      ) {
                        showStatementSection("accounts")
                        store.setMainView("statements")
                      } else {
                        store.setMainView("transactions")
                      }
                    }}
                  />
                </StatementRegister>
              )}
            </div>
            {reviewingAccounts && !savedBatchAccounts && caseId && (
              <ReferencedAccounts
                caseId={caseId}
                onOpenTransactions={(accountId) => {
                  resetPaymentTableView(caseId, { accountId })
                  applyInvestigationScope({ accountId })
                  store.setMode("transactions")
                  store.setMainView("transactions")
                }}
              />
            )}
            {reviewingAccounts && !savedBatchAccounts && (
              <section
                className="rounded-lg border p-3 space-y-3"
                aria-label="Account checks"
              >
                <h3 className="font-semibold">Account checks</h3>
                <p className="text-sm text-muted-foreground">
                  Check balances and missing statement periods across this case.
                  To review one statement, open it from Statement files.
                </p>
                {caseId && (
                  <ErrorBoundary level="section">
                    <OverviewStatementCoverage
                      caseId={caseId}
                      active={store.mainView === "statements" && reviewingAccounts}
                    />
                  </ErrorBoundary>
                )}
                <ErrorBoundary level="section">
                  <StatementCoveragePanel
                    key={`coverage:${caseId}`}
                    caseId={caseId}
                  />
                </ErrorBoundary>
                <Disclosure label="Balance checks for all accounts">
                  <ErrorBoundary level="section">
                    <StatementChecksPanel
                      onReviewStatement={reviewStatement}
                      key={`checks:${caseId}`}
                      caseId={caseId}
                    />
                  </ErrorBoundary>
                </Disclosure>
              </section>
            )}
          </div>
        </RetainedFinancialTab>

        <RetainedFinancialTab
          value="quarantine"
          className="flex min-h-0 flex-1 flex-col"
          active={store.mainView === "quarantine"}
        >
          <div className="min-h-0 flex-1 overflow-auto p-4">
            <ErrorBoundary level="section">
              <CorrectableLedger
                key={caseId}
                caseId={caseId}
                heldOut
                onAdjudicate={setAdjudicationRow}
              />
            </ErrorBoundary>
          </div>
        </RetainedFinancialTab>

        {/*
          The attempts tab takes no graph chrome either, for the same reason
          the ledger tab does not: it reads Postgres, and gating it on the
          graph query would hide the record of what was loaded from a case
          whose graph is empty -- which is a case whose loading may well be
          what went wrong.
        */}
        <RetainedFinancialTab
          value="runs"
          className="flex min-h-0 flex-1 flex-col"
          active={store.mainView === "runs"}
        >
          <div className="min-h-0 flex-1 overflow-auto p-4">
            <ErrorBoundary level="section">
              <IngestionRunsPanel caseId={caseId} />
            </ErrorBoundary>
          </div>
        </RetainedFinancialTab>

        {/*
          Reads Postgres, takes no graph chrome, is not gated on the graph
          query, for the same reasons as the three tabs above.

          It takes no `onAdjudicate` either, and that is the point of the
          separation rather than an omission: this is the record of decisions
          already taken, and the place a decision is taken is the dialog
          mounted below, outside this strip. Only the active tab's content is
          mounted, so a dialog opened from the ledger and living inside the
          ledger tab would be unmounted the moment anyone switched here.
        */}
        <RetainedFinancialTab
          value="decisions"
          className="flex min-h-0 flex-1 flex-col"
          active={store.mainView === "decisions"}
        >
          <div className="min-h-0 flex-1 overflow-auto p-4">
            <ErrorBoundary level="section">
              <DecisionsPanel caseId={caseId} />
            </ErrorBoundary>
          </div>
        </RetainedFinancialTab>

        <RetainedFinancialTab
          value="posting-graph"
          className="min-h-0 flex-1 overflow-auto"
          active={store.mainView === "posting-graph"}
        >
          <ErrorBoundary level="section">
            <LedgerPostingGraph key={caseId} caseId={caseId} />
          </ErrorBoundary>
        </RetainedFinancialTab>

        <RetainedFinancialTab
          value="findings"
          className="min-h-0 flex-1 overflow-auto"
          active={store.mainView === "findings"}
        >
          <FinancialFindings
            key={caseId}
            caseId={caseId}
            caseTitle={currentCase.data?.title || ""}
          />
        </RetainedFinancialTab>

        <RetainedFinancialTab
          value="transfers"
          className="min-h-0 flex-1 overflow-auto"
          active={store.mainView === "transfers"}
        >
          <ErrorBoundary level="section">
            <LedgerTransfersWorkbench key={caseId} caseId={caseId} />
          </ErrorBoundary>
        </RetainedFinancialTab>

        <RetainedFinancialTab
          value="transactions"
          forceMount
          style={
            store.mainView !== "transactions" ? { display: "none" } : undefined
          }
          className="flex min-h-0 flex-1 flex-col data-[state=inactive]:hidden"
          active={store.mainView === "transactions"}
        >
          <RecordsModeSwitch
            transactionsMode={isTransactionsMode}
            onChange={handleModeChange}
            aside={<FinancialAccessNotice inline />}
          />
          <div
            className="min-h-0 flex-1 space-y-4 overflow-auto p-4"
            style={!isTransactionsMode ? { display: "none" } : undefined}
          >
            {/* Buttons follow the title on its line, clear of the Controls tab at the right edge. */}
            <header className="flex flex-wrap items-center gap-3">
              <h2 className="text-lg font-semibold">
                Transactions
                <InfoTip text="All imported payments are available here. Filter by account or account holder, then open a payment to inspect its statement." />
              </h2>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={openAllPayments}>
                  Show all imported payments
                </Button>
                <Button onClick={() => store.setMainView("statements")}>
                  Add statements
                </Button>
              </div>
            </header>
            {importReceipt &&
              importReceipt.case_id === caseId &&
              (importReceipt.record_count ?? importReceipt.transaction_count) >
                0 && (
                <section
                  role="status"
                  className="rounded border border-primary/30 bg-primary/5 p-3 space-y-2"
                >
                  <p>
                    <strong>
                      {importReceipt.transaction_count} payments saved to
                      Transactions
                    </strong>{" "}
                    from {importReceipt.filename || "your statement"}.
                    {importReceipt.transaction_count
                      ? " Showing this statement’s payments."
                      : " No usable payments were identified in this import."}
                    {!!importReceipt.incomplete_count &&
                      ` ${importReceipt.incomplete_count} records have missing values and are kept outside totals.`}
                  </p>
                  <div className="flex gap-2">
                    {importReceipt.incomplete_count ===
                      (importReceipt.record_count ??
                        importReceipt.transaction_count) && (
                      <Button
                        variant="outline"
                        onClick={() =>
                          reviewStatement(importReceipt.evidence_file_id)
                        }
                      >
                        Review source statement
                      </Button>
                    )}
                    {importReceipt.account_id && (
                      <Button
                        variant="outline"
                        onClick={() => {
                          const scope = { accountId: importReceipt.account_id }
                          if (caseId) resetPaymentTableView(caseId, scope)
                          applyInvestigationScope(scope)
                          setImportReceipt(null)
                        }}
                      >
                        Show this account's payments
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      onClick={() => setImportReceipt(null)}
                    >
                      Dismiss
                    </Button>
                  </div>
                </section>
              )}
            <ErrorBoundary level="section">
              <CorrectableLedger
                investigation
                onReviewStatement={reviewStatement}
                key={caseId}
                caseId={caseId}
                onAdjudicate={setAdjudicationRow}
              />
            </ErrorBoundary>
          </div>
          {!isTransactionsMode && (
            <>
              <p className="border-b p-3 text-sm">
                These are amounts and claims found elsewhere in case evidence.
                They are separate from imported statement payments; correcting a
                statement payment does not change these records.
              </p>
              {graphTab(
                <>
                  <div className="flex min-h-0 flex-1 flex-col">
                    <div className="flex-1 overflow-auto">
                      <ErrorBoundary level="section">
                        <TransactionTable
                          caseId={caseId}
                          mode={store.mode}
                          transactions={pageTransactions}
                          allTransactions={filteredTransactions}
                          categories={categories}
                          sortColumns={store.sortColumns}
                          onCategorize={handleCategorize}
                          onAmountClick={handleAmountClick}
                          onEntityEdit={handleEntityEdit}
                          onGroupSubTransactions={handleGroupSubTransactions}
                          onRemoveFromGroup={handleRemoveFromGroup}
                          onSaveDetails={handleSaveDetails}
                        />
                      </ErrorBoundary>
                    </div>

                    <TablePagination
                      currentPage={visibleRecordsPage}
                      pageCount={pageCount}
                      pageSize={store.pageSize}
                      filteredCount={filteredCount}
                      onPageChange={store.setCurrentPage}
                      onPageSizeChange={store.setPageSize}
                    />
                  </div>
                </>
              )}
            </>
          )}
        </RetainedFinancialTab>

        <RetainedFinancialTab
          value="counterparties"
          className="flex min-h-0 flex-1 flex-col"
          active={store.mainView === "counterparties"}
        >
          <RecordsModeSwitch
            transactionsMode={isTransactionsMode}
            onChange={handleModeChange}
            aside={<FinancialAccessNotice inline />}
          />
          {isTransactionsMode ? (
            <div className="min-h-0 flex-1 overflow-auto">
              <ErrorBoundary level="section">
                {caseId && <InvestigatorPeople key={caseId} caseId={caseId} />}
              </ErrorBoundary>
            </div>
          ) : (
            <>
              <p className="border-b p-3 text-sm">
                These are amounts and claims found elsewhere in case evidence.
                They are separate from imported statement payments; correcting a
                statement payment does not change these records.
              </p>
              {graphTab(
                // Counterparty analysis covers statement payments only; for other records the tab says so.
                <div className="flex flex-1 items-center justify-center p-4">
                  <EmptyState
                    icon={Users}
                    title="Counterparty analysis is only available for transactions"
                    description="Select Statement payments above to examine who paid or received money."
                  />
                </div>
              )}
            </>
          )}
        </RetainedFinancialTab>

        <RetainedFinancialTab
          value="patterns"
          className="min-h-0 flex-1 overflow-auto"
          active={store.mainView === "patterns"}
        >
          <ErrorBoundary level="section">
            <FinancialPatternReview key={caseId} caseId={caseId} />
          </ErrorBoundary>
        </RetainedFinancialTab>
        <RetainedFinancialTab
          value="case-context"
          className="min-h-0 flex-1 overflow-auto"
          active={store.mainView === "case-context"}
        >
          <ErrorBoundary level="section">
            <FinancialCaseTimeline key={caseId} caseId={caseId} />
          </ErrorBoundary>
        </RetainedFinancialTab>
        <RetainedFinancialTab
          value="tracing"
          className="min-h-0 flex-1 overflow-auto"
          active={store.mainView === "tracing"}
        >
          <ErrorBoundary level="section">
            <LedgerTracingWorkbench key={caseId} caseId={caseId} />
          </ErrorBoundary>
        </RetainedFinancialTab>

        <RetainedFinancialTab
          value="trends"
          className="flex min-h-0 flex-1 flex-col"
          active={store.mainView === "trends"}
        >
          <RecordsModeSwitch
            transactionsMode={isTransactionsMode}
            onChange={handleModeChange}
            aside={<FinancialAccessNotice inline />}
          />
          {isTransactionsMode ? (
            <div className="min-h-0 flex-1 overflow-auto">
              <ErrorBoundary level="section">
                {caseId && <InvestigatorTrends key={caseId} caseId={caseId} active={store.mainView === "trends"} />}
              </ErrorBoundary>
            </div>
          ) : (
            <>
              <p className="border-b p-3 text-sm">
                These are amounts and claims found elsewhere in case evidence.
                They are separate from imported statement payments; correcting a
                statement payment does not change these records.
              </p>
              {graphTab(
                <>
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
                    <div>
                      <h2 className="text-sm font-semibold">Trends</h2>
                      <p className="text-xs text-muted-foreground">
                        Compare recorded amounts by date and category. Choose a
                        currency below and a time interval on the right.
                      </p>
                    </div>
                    <div className="flex items-center rounded-md border border-border p-0.5">
                      {(["auto", "daily", "weekly", "monthly"] as const).map(
                        (grouping) => (
                          <button
                            key={grouping}
                            className={`rounded px-2 py-1 text-xs transition ${
                              store.chartGrouping === grouping
                                ? "bg-secondary text-secondary-foreground"
                                : "text-muted-foreground hover:text-foreground"
                            }`}
                            onClick={() => store.setChartGrouping(grouping)}
                          >
                            {grouping === "auto"
                              ? "Auto"
                              : grouping.charAt(0).toUpperCase() +
                                grouping.slice(1)}
                          </button>
                        )
                      )}
                    </div>
                  </div>

                  <div className="min-h-0 flex-1 overflow-auto p-4">
                    {filteredTransactions.length === 0 ? (
                      <div className="flex h-full items-center justify-center">
                        <EmptyState
                          icon={BarChart3}
                          title="No trend data matches the current filters"
                          description="Adjust the active filters to restore chart data."
                        />
                      </div>
                    ) : (
                      <ErrorBoundary level="section">
                        <FinancialCharts
                          transactions={filteredTransactions}
                          categories={categories}
                          groupingOverride={store.chartGrouping}
                        />
                      </ErrorBoundary>
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </RetainedFinancialTab>
      </Tabs>
      </FinancialResetSlotProvider>

      <BulkCategorizeDialog
        open={bulkCategorizeOpen}
        onOpenChange={setBulkCategorizeOpen}
        selectedCount={store.checkedKeys.size}
        categories={categories}
        onApply={handleBulkCategorize}
        isPending={batchCategorize.isPending}
      />

      <CategoryManagementDialog
        caseId={caseId!}
        open={categoryMgmtOpen}
        onOpenChange={setCategoryMgmtOpen}
        categories={categories}
        onCreateCategory={handleCreateCategory}
      />

      <SubTransactionDialog
        open={subTxDialogOpen}
        onOpenChange={setSubTxDialogOpen}
        parent={subTxParent}
        subTransactions={subTransactions}
        allTransactions={filteredTransactions}
        onLink={(childKey) =>
          subTxParent &&
          linkSub.mutate({ parentKey: subTxParent.key, childKey })
        }
        onUnlink={(childKey) => unlinkSub.mutate({ childKey })}
      />

      {/* A link to one payment (?payment=<id>, e.g. a ledger row the AI agent cited) opens that payment. */}
      {linkedPayment && caseId && (
        <LedgerSourceDialog
          caseId={caseId}
          transactionId={linkedPayment}
          onClose={() =>
            setParams(
              (current) => {
                const next = new URLSearchParams(current)
                next.delete("payment")
                return next
              },
              { replace: true }
            )
          }
        />
      )}

      <AmountEditDialog
        caseId={caseId!}
        open={amountEditOpen}
        onOpenChange={setAmountEditOpen}
        transaction={amountEditTx}
        onSave={handleAmountSave}
        isPending={updateAmount.isPending}
      />

      <EntityEditDialog
        open={entityEditOpen}
        onOpenChange={setEntityEditOpen}
        field={entityEditField}
        allEntities={caseEntities}
        transactionKeys={entityEditKeys}
        onSave={handleEntitySave}
        isPending={setFromTo.isPending || batchSetFromTo.isPending}
      />

      <BulkImportDialog
        key={`financial-corrections:${caseId}`}
        open={bulkImportOpen}
        onOpenChange={setBulkImportOpen}
        transactions={filteredTransactions}
        onSubmit={handleBulkImport}
        isPending={bulkCorrect.isPending}
      />

      {/*
        Outside the tab strip, like every other dialog here, and for a reason
        that bites harder in this one case: only the active tab's content is
        mounted, so a dialog rendered inside a tab is destroyed by a change of
        tab. It is also outside the panel that owns the row, because a change
        that succeeds takes the row out of that panel's list.

        Mounted on this page's own state and nothing else. The row goes on
        being passed to the dialog after it has left every list on screen,
        which is what keeps the answer readable; `null` here means the person
        closed the dialog, and only that.
      */}
      {adjudicationRow !== null && (
        <RowAdjudicationDialog
          caseId={caseId}
          row={adjudicationRow}
          open
          onClose={() => setAdjudicationRow(null)}
        />
      )}
    </div>
  )
}
import { AccountOwnershipReview } from "./AccountOwnershipReview"
