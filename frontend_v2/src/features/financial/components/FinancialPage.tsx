import { useState, useCallback } from "react"
import { useParams } from "react-router-dom"
import { DollarSign } from "lucide-react"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { ErrorBoundary } from "@/components/ui/error-boundary"
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
import { FinancialToolbar } from "./FinancialToolbar"
import { FinancialFilterPanel } from "./FinancialFilterPanel"
import { FinancialSummaryCards } from "./FinancialSummaryCards"
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
  const { data: transactionsResponse, isLoading } = useTransactions(caseId, { mode: store.mode })
  const { data: categories = [] } = useFinancialCategories(caseId, store.mode)
  const { data: caseEntities = [] } = useFinancialEntities(caseId)
  const transactions = transactionsResponse?.transactions ?? []
  const usesLegacyFinancialModel = transactionsResponse?.uses_legacy_financial_model ?? false
  const isTransactionsMode = store.mode === "transactions"

  // Mutations
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

  // Filter pipeline
  const {
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
    minAmount: store.minAmount,
    maxAmount: store.maxAmount,
    sortColumns: store.sortColumns,
    pageSize: store.pageSize,
    currentPage: store.currentPage,
  })

  // Dialog state
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

  // Handlers
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

  const handleGroupSubTransactions = useCallback(
    (tx: Transaction) => {
      setSubTxParent(tx)
      setSubTxDialogOpen(true)
    },
    []
  )

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
    (corrections: { node_key: string; new_amount: number; correction_reason: string }[]) => {
      bulkCorrect.mutate(corrections, {
        onSuccess: () => setBulkImportOpen(false),
      })
    },
    [bulkCorrect]
  )

  // Loading state
  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  // Empty state
  if (!transactions.length) {
    return (
      <EmptyState
        icon={DollarSign}
        title={isTransactionsMode ? "No documentary transactions" : "No financial intelligence"}
        description={
          isTransactionsMode
            ? "Process evidence with documentary financial records to populate this view"
            : "Process evidence with financial signals, valuations, or alleged totals to populate this view"
        }
      />
    )
  }

  // Sub-transactions for dialog
  const subTransactions = subTxParent
    ? (transactions || []).filter(
        (t) => t.parent_transaction_key === subTxParent.key
      )
    : []

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <FinancialToolbar
        mode={store.mode}
        filteredCount={filteredCount}
        totalCount={transactions.length}
        caseId={caseId!}
        onOpenBulkImport={() => setBulkImportOpen(true)}
        onOpenCategoryManagement={() => setCategoryMgmtOpen(true)}
      />

      {usesLegacyFinancialModel && (
        <div className="border-b border-amber-500/20 bg-amber-500/10 px-4 py-2 text-xs text-amber-100">
          This case is using the legacy financial dataset. Reprocess the case to get strict evidence-backed transactions and provenance-aware financial intelligence.
        </div>
      )}

      {/* Filter Panel */}
      <FinancialFilterPanel
        categories={categories}
        categoryCounts={categoryCounts}
        allEntities={caseEntities}
      />

      {/* Summary Cards */}
      <FinancialSummaryCards
        transactions={filteredTransactions}
        entityFilter={store.entityFilter}
        mode={store.mode}
      />

      {/* Bulk Actions */}
      {isTransactionsMode && (
        <BulkActionsBar
          onBulkCategorize={() => setBulkCategorizeOpen(true)}
          onBulkSetFrom={handleBulkSetFrom}
          onBulkSetTo={handleBulkSetTo}
        />
      )}

      {/* Charts */}
      {store.chartsPanelOpen && (
        <ErrorBoundary level="section">
          <FinancialCharts
            transactions={filteredTransactions}
            categories={categories}
          />
        </ErrorBoundary>
      )}

      {/* Table + Pagination */}
      <div className="flex flex-1 flex-col min-h-0">
        <div className="flex-1 overflow-auto">
          <ErrorBoundary level="section">
            <TransactionTable
              mode={store.mode}
              transactions={pageTransactions}
              allTransactions={transactions}
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

        {/* Pagination */}
        <TablePagination
          currentPage={store.currentPage}
          pageCount={pageCount}
          pageSize={store.pageSize}
          filteredCount={filteredCount}
          onPageChange={store.setCurrentPage}
          onPageSizeChange={store.setPageSize}
        />
      </div>

      {/* Dialogs */}
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
        allTransactions={transactions}
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
