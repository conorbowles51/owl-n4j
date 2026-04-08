import { useCallback, useEffect, useMemo, useState } from "react"
import { useParams } from "react-router-dom"
import {
  BarChart3,
  DollarSign,
  Rows3,
  Users,
} from "lucide-react"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { ErrorBoundary } from "@/components/ui/error-boundary"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useFinancialStore } from "../stores/financial.store"
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
import { BulkCategorizeDialog } from "./BulkCategorizeDialog"
import { CategoryManagementDialog } from "./CategoryManagementDialog"
import { SubTransactionDialog } from "./SubTransactionDialog"
import { AmountEditDialog } from "./AmountEditDialog"
import { EntityEditDialog } from "./EntityEditDialog"
import { BulkImportDialog } from "./BulkImportDialog"
import { TablePagination } from "@/features/table/components/TablePagination"
import type { Transaction } from "../api"

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

  useEffect(() => {
    if (!isTransactionsMode) {
      setSelectedSenders(new Set())
      setSelectedBeneficiaries(new Set())
    }
  }, [isTransactionsMode])

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

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!transactions.length) {
    return (
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
    )
  }

  const subTransactions = subTxParent
    ? transactions.filter((t) => t.parent_transaction_key === subTxParent.key)
    : []

  return (
    <div className="flex h-full flex-col">
      <FinancialToolbar
        mode={store.mode}
        filteredCount={filteredCount}
        totalCount={transactions.length}
        onOpenBulkImport={() => setBulkImportOpen(true)}
        onOpenCategoryManagement={() => setCategoryMgmtOpen(true)}
        onExportPdf={handleExportPdf}
      />

      {usesLegacyFinancialModel && (
        <div className="border-b border-amber-500/20 bg-amber-500/10 px-4 py-2 text-xs text-amber-100">
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

      <Tabs
        value={store.mainView}
        onValueChange={(value) =>
          store.setMainView(value as "transactions" | "counterparties" | "trends")
        }
        className="flex min-h-0 flex-1 flex-col"
      >
        <div className="border-b border-border px-4">
          <TabsList variant="line" className="h-10">
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

        <TabsContent value="transactions" className="flex min-h-0 flex-1 flex-col">
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
        </TabsContent>

        <TabsContent value="counterparties" className="flex min-h-0 flex-1 flex-col">
          {!isTransactionsMode ? (
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
          )}
        </TabsContent>

        <TabsContent value="trends" className="flex min-h-0 flex-1 flex-col">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold">Trends</h2>
              <p className="text-xs text-muted-foreground">
                Full-width volume and category views for the current filtered set.
              </p>
            </div>
            <div className="flex items-center rounded-md border border-border p-0.5">
              {(["auto", "daily", "weekly", "monthly"] as const).map((grouping) => (
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
              ))}
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
    </div>
  )
}
