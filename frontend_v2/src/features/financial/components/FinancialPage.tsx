import { useCallback, useMemo, useState, type ReactNode } from "react"
import { useParams } from "react-router-dom"
import {
  BarChart3,
  DollarSign,
  Gavel,
  History,
  Rows3,
  ScrollText,
  ShieldAlert,
  Users,
} from "lucide-react"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { ErrorBoundary } from "@/components/ui/error-boundary"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
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
import { buildEntityFlowRows } from "../lib/filter-transactions"
import { FinancialToolbar } from "./FinancialToolbar"
import { FinancialFilterPanel } from "./FinancialFilterPanel"
import { FinancialSummaryCards } from "./FinancialSummaryCards"
import { EntityFlowTables } from "./EntityFlowTables"
import { BulkActionsBar } from "./BulkActionsBar"
import { TransactionTable } from "./TransactionTable"
import { FinancialCharts } from "./FinancialCharts"
import { LedgerPanel } from "./LedgerPanel"
import { QuarantinePanel } from "./QuarantinePanel"
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

export function FinancialPage() {
  const { id: caseId } = useParams()
  const store = useFinancialStore()
  const { data: transactionsResponse, isLoading } = useTransactions(caseId, {
    mode: store.mode,
  })
  const { data: categories = [] } = useFinancialCategories(caseId, store.mode)
  const { data: caseEntities = [] } = useFinancialEntities(caseId)
  const transactions = transactionsResponse?.transactions ?? []
  const usesLegacyFinancialModel =
    transactionsResponse?.uses_legacy_financial_model ?? false
  const isTransactionsMode = store.mode === "transactions"
  const [selectedSenders, setSelectedSenders] = useState<Set<string>>(new Set())
  const [selectedBeneficiaries, setSelectedBeneficiaries] = useState<Set<string>>(
    new Set()
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
    baseFilteredTransactions,
    filteredTransactions,
    pageTransactions,
    filteredCount,
    pageCount,
    categoryCounts,
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

  const senderRows = useMemo(
    () => buildEntityFlowRows(baseFilteredTransactions, "from", selectedBeneficiaries),
    [baseFilteredTransactions, selectedBeneficiaries]
  )
  const beneficiaryRows = useMemo(
    () => buildEntityFlowRows(baseFilteredTransactions, "to", selectedSenders),
    [baseFilteredTransactions, selectedSenders]
  )

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
  const [adjudicationRow, setAdjudicationRow] = useState<LedgerTransaction | null>(
    null
  )

  const handleCategorize = useCallback(
    (nodeKey: string, category: string) => {
      categorize.mutate({ nodeKey, category })
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
    (newAmount: number, correctionReason: string) => {
      if (!amountEditTx) return
      updateAmount.mutate(
        { nodeKey: amountEditTx.key, newAmount, correctionReason },
        { onSuccess: () => setAmountEditOpen(false) }
      )
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

  const handleBulkSetFrom = useCallback(() => {
    setEntityEditField("from")
    setEntityEditKeys(Array.from(store.checkedKeys))
    setEntityEditOpen(true)
  }, [store.checkedKeys])

  const handleBulkSetTo = useCallback(() => {
    setEntityEditField("to")
    setEntityEditKeys(Array.from(store.checkedKeys))
    setEntityEditOpen(true)
  }, [store.checkedKeys])

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
      createCategory.mutate({ name, color })
    },
    [createCategory]
  )

  const handleBulkImport = useCallback(
    (
      corrections: {
        node_key: string
        new_amount: number
        correction_reason: string
      }[]
    ) => {
      bulkCorrect.mutate(corrections, {
        onSuccess: () => setBulkImportOpen(false),
      })
    },
    [bulkCorrect]
  )

  const handleModeChange = useCallback(
    (mode: FinancialDatasetMode) => {
      store.setMode(mode)
      setSelectedSenders(new Set())
      setSelectedBeneficiaries(new Set())
    },
    [store]
  )

  const handleSelectedSendersChange = useCallback(
    (value: Set<string>) => {
      setSelectedSenders(value)
      store.setCurrentPage(0)
    },
    [store]
  )

  const handleSelectedBeneficiariesChange = useCallback(
    (value: Set<string>) => {
      setSelectedBeneficiaries(value)
      store.setCurrentPage(0)
    },
    [store]
  )

  const handleExportPdf = useCallback(() => {
    if (!caseId) return

    const params = new URLSearchParams({
      case_id: caseId,
      mode: store.mode,
      include_entity_notes: "true",
    })

    if (store.selectedCategories.size > 0) {
      params.set("categories", [...store.selectedCategories].join(","))
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
      params.set("from_entities", [...selectedSenders].join(","))
    }
    if (selectedBeneficiaries.size > 0) {
      params.set("to_entities", [...selectedBeneficiaries].join(","))
    }

    window.open(`/api/financial/export/pdf?${params.toString()}`, "_blank")
  }, [
    caseId,
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
        onModeChange={handleModeChange}
      />

      {usesLegacyFinancialModel && (
        <div className="border-b border-yellow-500/25 bg-yellow-500/10 px-4 py-2 text-xs text-yellow-800 dark:text-yellow-200">
          This case is using the legacy financial dataset. Reprocess the case to
          get strict evidence-backed transactions and provenance-aware financial
          intelligence.
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
        <div className="flex flex-1 items-center justify-center">
          <LoadingSpinner size="lg" />
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
                : "No financial intelligence"
            }
            description={
              isTransactionsMode
                ? "Process evidence with documentary financial records to populate this view"
                : "Process evidence with financial signals, valuations, or alleged totals to populate this view"
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
      <Tabs
        value={store.mainView}
        onValueChange={(value) => store.setMainView(value as FinancialMainView)}
        className="flex min-h-0 flex-1 flex-col"
      >
        <div className="border-b border-border bg-card px-4">
          <TabsList variant="line" className="h-10">
            <TabsTrigger value="ledger" data-testid="financial-tab-ledger">
              <ScrollText className="size-3.5" />
              Ledger
            </TabsTrigger>
            {/*
              Directly after the ledger because the two are one read against
              two populations: what this case's totals count, and what they
              leave out. A person who has just read a total is one tab away
              from what the total excludes.
            */}
            <TabsTrigger value="quarantine" data-testid="financial-tab-quarantine">
              <ShieldAlert className="size-3.5" />
              Held out
            </TabsTrigger>
            {/*
              Kept beside the ledger, and before the three graph tabs, because
              it reads the same store the ledger does: it is the record of what
              put the rows there. "Attempts" is the word the notice above the
              ledger already uses in front of a reader; "runs" is the word the
              endpoint, the hook and the store member use.
            */}
            <TabsTrigger value="runs" data-testid="financial-tab-runs">
              <History className="size-3.5" />
              Attempts
            </TabsTrigger>
            {/*
              Last of the four Postgres tabs, and still before the graph tabs.
              The three before it are views of what the ledger holds now; this
              one is the record of who moved any of it and on what grounds, so
              it is a tab away from the totals it explains rather than the
              other side of the strip.
            */}
            <TabsTrigger value="decisions" data-testid="financial-tab-decisions">
              <Gavel className="size-3.5" />
              Decisions
            </TabsTrigger>
            <TabsTrigger value="transactions">
              <Rows3 className="size-3.5" />
              Transactions
            </TabsTrigger>
            <TabsTrigger value="counterparties">
              <Users className="size-3.5" />
              Counterparties
            </TabsTrigger>
            <TabsTrigger value="trends">
              <BarChart3 className="size-3.5" />
              Trends
            </TabsTrigger>
          </TabsList>
        </div>

        {/*
          The ledger tab reads Postgres and shares nothing with the three graph
          tabs: not the query, not the filters, not the counts. It deliberately
          takes none of the graph chrome and is not gated on the graph query,
          so a case with ledger rows and no graph opens here and shows them.
        */}
        <TabsContent value="ledger" className="flex min-h-0 flex-1 flex-col">
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
              <LedgerPanel caseId={caseId} onAdjudicate={setAdjudicationRow} />
            </ErrorBoundary>
          </div>
        </TabsContent>

        {/*
          Reads Postgres like the ledger tab, takes no graph chrome and is not
          gated on the graph query, for the same reasons. The notice above the
          ledger is not repeated here: it explains why a ledger might be short,
          and nothing about a failed attempt to load evidence bears on whether
          the rows that did arrive are being held out of the totals.
        */}
        <TabsContent value="quarantine" className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-auto p-4">
            <ErrorBoundary level="section">
              <QuarantinePanel caseId={caseId} onAdjudicate={setAdjudicationRow} />
            </ErrorBoundary>
          </div>
        </TabsContent>

        {/*
          The attempts tab takes no graph chrome either, for the same reason
          the ledger tab does not: it reads Postgres, and gating it on the
          graph query would hide the record of what was loaded from a case
          whose graph is empty -- which is a case whose loading may well be
          what went wrong.
        */}
        <TabsContent value="runs" className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-auto p-4">
            <ErrorBoundary level="section">
              <IngestionRunsPanel caseId={caseId} />
            </ErrorBoundary>
          </div>
        </TabsContent>

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
        <TabsContent value="decisions" className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-auto p-4">
            <ErrorBoundary level="section">
              <DecisionsPanel caseId={caseId} />
            </ErrorBoundary>
          </div>
        </TabsContent>

        <TabsContent value="transactions" className="flex min-h-0 flex-1 flex-col">
          {graphTab(
            <>
              {isTransactionsMode && (
                <BulkActionsBar
                  onBulkCategorize={() => setBulkCategorizeOpen(true)}
                  onBulkSetFrom={handleBulkSetFrom}
                  onBulkSetTo={handleBulkSetTo}
                />
              )}

              <div className="flex min-h-0 flex-1 flex-col">
                <div className="flex-1 overflow-auto">
                  <ErrorBoundary level="section">
                    <TransactionTable
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
                  currentPage={store.currentPage}
                  pageCount={pageCount}
                  pageSize={store.pageSize}
                  filteredCount={filteredCount}
                  onPageChange={store.setCurrentPage}
                  onPageSizeChange={store.setPageSize}
                />
              </div>
            </>
          )}
        </TabsContent>

        <TabsContent value="counterparties" className="flex min-h-0 flex-1 flex-col">
          {graphTab(
            !isTransactionsMode ? (
              <div className="flex flex-1 items-center justify-center p-4">
                <EmptyState
                  icon={Users}
                  title="Counterparty analysis is only available for transactions"
                  description="Switch to documentary transactions mode to explore sender and beneficiary relationships."
                />
              </div>
            ) : baseFilteredTransactions.length === 0 ? (
              <div className="flex flex-1 items-center justify-center p-4">
                <EmptyState
                  icon={Users}
                  title="No counterparties match the current filters"
                  description="Adjust the active search, category, date, entity, or amount filters to populate the sender and beneficiary analysis."
                />
              </div>
            ) : (
              <div className="min-h-0 flex-1 overflow-hidden p-4">
                <EntityFlowTables
                  className="h-full"
                  senders={senderRows}
                  beneficiaries={beneficiaryRows}
                  selectedSenders={selectedSenders}
                  selectedBeneficiaries={selectedBeneficiaries}
                  onSelectedSendersChange={handleSelectedSendersChange}
                  onSelectedBeneficiariesChange={handleSelectedBeneficiariesChange}
                />
              </div>
            )
          )}
        </TabsContent>

        <TabsContent value="trends" className="flex min-h-0 flex-1 flex-col">
          {graphTab(
            <>
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
                <div>
                  <h2 className="text-sm font-semibold">Trends</h2>
                  <p className="text-xs text-muted-foreground">
                    Full-width volume and category views for the current filtered
                    set.
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
                          : grouping.charAt(0).toUpperCase() + grouping.slice(1)}
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
        </TabsContent>
      </Tabs>

      <BulkCategorizeDialog
        open={bulkCategorizeOpen}
        onOpenChange={setBulkCategorizeOpen}
        selectedCount={store.checkedKeys.size}
        categories={categories}
        onApply={handleBulkCategorize}
        isPending={batchCategorize.isPending}
      />

      <CategoryManagementDialog
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
          subTxParent && linkSub.mutate({ parentKey: subTxParent.key, childKey })
        }
        onUnlink={(childKey) => unlinkSub.mutate({ childKey })}
      />

      <AmountEditDialog
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
        open={bulkImportOpen}
        onOpenChange={setBulkImportOpen}
        transactions={transactions}
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
