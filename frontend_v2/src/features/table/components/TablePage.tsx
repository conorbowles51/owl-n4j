import { useState, useCallback, useRef, useMemo } from "react"
import { useParams } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { useGraphData } from "@/features/graph/hooks/use-graph-data"
import { useGraphStore } from "@/stores/graph.store"
import { useUIStore } from "@/stores/ui.store"
import { useCaseStore } from "@/stores/case.store"
import { graphAPI } from "@/features/graph/api"
import { useTableStore } from "../stores/table.store"
import { useTableColumns } from "../hooks/use-table-columns"
import { useFilteredSortedNodes } from "../hooks/use-filtered-sorted-nodes"
import { useCsvExport } from "../hooks/use-csv-export"
import { useKeyboardNavigation } from "../hooks/use-keyboard-navigation"
import { TableToolbar } from "./TableToolbar"
import { TableGrid } from "./TableGrid"
import { BulkActionsBar } from "./BulkActionsBar"
import { BulkEditDialog } from "./BulkEditDialog"
import { TablePagination } from "./TablePagination"
import type { ColumnConfig } from "./TableColumnConfig"
import { MergeEntitiesDialog } from "@/features/graph/components/MergeEntitiesDialog"
import { AddNodeDialog } from "@/features/graph/components/AddNodeDialog"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"

export function TablePage() {
  const { id: caseId } = useParams()
  const queryClient = useQueryClient()
  const { data: graphData, isLoading } = useGraphData(caseId)

  // Graph store: selection -> side panel
  const selectNodes = useGraphStore((s) => s.selectNodes)
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const expandGraphPanelTo = useUIStore((s) => s.expandGraphPanelTo)
  const caseName = useCaseStore((s) => s.currentCaseName)

  // Table store
  const searchTerm = useTableStore((s) => s.searchTerm)
  const selectedTypes = useTableStore((s) => s.selectedTypes)
  const sortColumns = useTableStore((s) => s.sortColumns)
  const pageSize = useTableStore((s) => s.pageSize)
  const currentPage = useTableStore((s) => s.currentPage)
  const checkedKeys = useTableStore((s) => s.checkedKeys)
  const lastClickedKey = useTableStore((s) => s.lastClickedKey)
  const columnOrder = useTableStore((s) => s.columnOrder)
  const typeFilterOpen = useTableStore((s) => s.typeFilterOpen)

  const setSearchTerm = useTableStore((s) => s.setSearchTerm)
  const toggleType = useTableStore((s) => s.toggleType)
  const selectAllTypes = useTableStore((s) => s.selectAllTypes)
  const clearTypes = useTableStore((s) => s.clearTypes)
  const toggleSort = useTableStore((s) => s.toggleSort)
  const setPageSize = useTableStore((s) => s.setPageSize)
  const setCurrentPage = useTableStore((s) => s.setCurrentPage)
  const toggleChecked = useTableStore((s) => s.toggleChecked)
  const setCheckedKeys = useTableStore((s) => s.setCheckedKeys)
  const checkRange = useTableStore((s) => s.checkRange)
  const clearChecked = useTableStore((s) => s.clearChecked)
  const setLastClickedKey = useTableStore((s) => s.setLastClickedKey)
  const setColumnOrder = useTableStore((s) => s.setColumnOrder)
  const setTypeFilterOpen = useTableStore((s) => s.setTypeFilterOpen)

  // Dialogs
  const [mergeOpen, setMergeOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [bulkEditOpen, setBulkEditOpen] = useState(false)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Refs
  const searchInputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Data
  const nodes = graphData?.nodes ?? []
  const edges = graphData?.edges ?? []

  // Column discovery
  const { allColumns } = useTableColumns(nodes)

  // Filter pipeline
  const {
    filteredNodes,
    pageNodes,
    totalCount,
    filteredCount,
    pageCount,
    typeCounts,
    connectionCounts,
    sourceCounts,
  } = useFilteredSortedNodes({
    nodes,
    edges,
    searchTerm,
    selectedTypes,
    sortColumns,
    pageSize,
    currentPage,
  })

  // Clamp current page
  const effectivePage = Math.min(currentPage, Math.max(0, pageCount - 1))
  if (effectivePage !== currentPage && pageCount > 0) {
    setCurrentPage(effectivePage)
  }

  // Visible columns based on columnOrder
  const visibleColumns = useMemo(() => {
    const orderSet = new Set(columnOrder)
    // Always include checkbox
    const cols = allColumns.filter(
      (c) => c.key === "_checkbox" || orderSet.has(c.key)
    )
    // Sort by order
    return cols.sort((a, b) => {
      if (a.key === "_checkbox") return -1
      if (b.key === "_checkbox") return 1
      const aIdx = columnOrder.indexOf(a.key)
      const bIdx = columnOrder.indexOf(b.key)
      return aIdx - bIdx
    })
  }, [allColumns, columnOrder])

  // Column config for TableColumnConfig
  const columnConfigs: ColumnConfig[] = useMemo(() => {
    const orderSet = new Set(columnOrder)
    return allColumns
      .filter((c) => c.key !== "_checkbox")
      .map((c) => ({
        key: c.key,
        label: c.label,
        visible: orderSet.has(c.key),
      }))
  }, [allColumns, columnOrder])

  const handleColumnsChange = useCallback(
    (configs: ColumnConfig[]) => {
      setColumnOrder(configs.filter((c) => c.visible).map((c) => c.key))
    },
    [setColumnOrder]
  )

  // Entity selection -> side panel
  const selectedNodeKey = useMemo(() => {
    const keys = Array.from(selectedNodeKeys)
    return keys.length === 1 ? keys[0] : null
  }, [selectedNodeKeys])

  const handleSelectNode = useCallback(
    (key: string) => {
      selectNodes([key])
      expandGraphPanelTo("detail")
    },
    [selectNodes, expandGraphPanelTo]
  )

  // Checkbox range select
  const handleCheckRange = useCallback(
    (key: string) => {
      if (!lastClickedKey) {
        toggleChecked(key)
        return
      }
      const allKeys = filteredNodes.map((n) => n.key)
      const startIdx = allKeys.indexOf(lastClickedKey)
      const endIdx = allKeys.indexOf(key)
      if (startIdx === -1 || endIdx === -1) {
        toggleChecked(key)
        return
      }
      const from = Math.min(startIdx, endIdx)
      const to = Math.max(startIdx, endIdx)
      checkRange(allKeys.slice(from, to + 1))
      setLastClickedKey(key)
    },
    [lastClickedKey, filteredNodes, toggleChecked, checkRange, setLastClickedKey]
  )

  // Grid row shift+click range
  const handleGridCheckRange = useCallback(
    (startKey: string, _endKey: string) => {
      handleCheckRange(startKey)
    },
    [handleCheckRange]
  )

  // Toggle all on current page
  const allPageChecked = pageNodes.length > 0 && pageNodes.every((n) => checkedKeys.has(n.key))
  const somePageChecked = pageNodes.some((n) => checkedKeys.has(n.key))

  const handleToggleAllChecked = useCallback(() => {
    if (allPageChecked) {
      // Uncheck all on page
      const pageKeySet = new Set(pageNodes.map((n) => n.key))
      const next = new Set(checkedKeys)
      for (const k of pageKeySet) next.delete(k)
      setCheckedKeys(next)
    } else {
      // Check all on page
      checkRange(pageNodes.map((n) => n.key))
    }
  }, [allPageChecked, pageNodes, checkedKeys, setCheckedKeys, checkRange])

  // Select all (keyboard Ctrl+A)
  const handleSelectAll = useCallback(() => {
    checkRange(pageNodes.map((n) => n.key))
  }, [checkRange, pageNodes])

  const handleClearSelection = useCallback(() => {
    clearChecked()
    selectNodes([])
  }, [clearChecked, selectNodes])

  // CSV export
  const { exportCSV } = useCsvExport()
  const handleExportCSV = useCallback(() => {
    const date = new Date().toISOString().slice(0, 10)
    const name = (caseName ?? "case").replace(/\s+/g, "-").toLowerCase()
    exportCSV({
      nodes: filteredNodes,
      columns: visibleColumns,
      connectionCounts,
      sourceCounts,
      filename: `${name}-entities-${date}.csv`,
    })
  }, [exportCSV, filteredNodes, visibleColumns, connectionCounts, sourceCounts, caseName])

  // Bulk actions
  const checkedArray = useMemo(() => Array.from(checkedKeys), [checkedKeys])
  const checkedNodes = useMemo(
    () => nodes.filter((n) => checkedKeys.has(n.key)),
    [nodes, checkedKeys]
  )

  const handleMerge = useCallback(() => {
    if (checkedArray.length === 2) setMergeOpen(true)
  }, [checkedArray])

  const handleDelete = useCallback(() => {
    if (checkedArray.length > 0) setDeleteConfirmOpen(true)
  }, [checkedArray])

  const confirmDelete = useCallback(async () => {
    if (!caseId) return
    setDeleting(true)
    try {
      await Promise.all(
        checkedArray.map((key) => graphAPI.deleteNode(key, caseId))
      )
      clearChecked()
      queryClient.invalidateQueries({ queryKey: ["graph", caseId] })
    } finally {
      setDeleting(false)
      setDeleteConfirmOpen(false)
    }
  }, [checkedArray, caseId, clearChecked, queryClient])

  const handleBulkEditComplete = useCallback(() => {
    if (caseId) {
      queryClient.invalidateQueries({ queryKey: ["graph", caseId] })
    }
  }, [caseId, queryClient])

  const handleMerged = useCallback(() => {
    clearChecked()
    if (caseId) {
      queryClient.invalidateQueries({ queryKey: ["graph", caseId] })
    }
  }, [clearChecked, caseId, queryClient])

  const handleCreated = useCallback(() => {
    if (caseId) {
      queryClient.invalidateQueries({ queryKey: ["graph", caseId] })
    }
  }, [caseId, queryClient])

  // Known property keys for bulk edit
  const knownProperties = useMemo(() => {
    const props = new Set<string>()
    for (const node of nodes) {
      for (const key of Object.keys(node.properties)) {
        props.add(key)
      }
    }
    return Array.from(props).sort()
  }, [nodes])

  // Type filter helpers
  const handleSelectAllTypes = useCallback(() => {
    clearTypes()
  }, [clearTypes])

  // Keyboard navigation
  useKeyboardNavigation({
    pageNodes,
    onSelectNode: handleSelectNode,
    onToggleChecked: toggleChecked,
    onCheckRange: (keys: string[]) => checkRange(keys),
    onSelectAll: handleSelectAll,
    onClearSelection: handleClearSelection,
    searchInputRef,
    containerRef,
    enabled: !mergeOpen && !addOpen && !bulkEditOpen && !deleteConfirmOpen,
  })

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <TableToolbar
        searchTerm={searchTerm}
        onSearchChange={setSearchTerm}
        typeFilterOpen={typeFilterOpen}
        onTypeFilterOpenChange={setTypeFilterOpen}
        typeCounts={typeCounts}
        selectedTypes={selectedTypes}
        onToggleType={toggleType}
        onSelectAllTypes={handleSelectAllTypes}
        onClearTypes={() => clearTypes()}
        columns={columnConfigs}
        onColumnsChange={handleColumnsChange}
        filteredCount={filteredCount}
        totalCount={totalCount}
        onExportCSV={handleExportCSV}
        onAddEntity={() => setAddOpen(true)}
        searchInputRef={searchInputRef}
      />

      <BulkActionsBar
        count={checkedKeys.size}
        onMerge={handleMerge}
        onDelete={handleDelete}
        onBulkEdit={() => setBulkEditOpen(true)}
        onClear={clearChecked}
      />

      {filteredCount === 0 ? (
        <div className="flex flex-1 items-center justify-center">
          <EmptyState
            title="No entities found"
            description={
              searchTerm || selectedTypes.size > 0
                ? "Try adjusting your filters"
                : "No data available"
            }
          />
        </div>
      ) : (
        <TableGrid
          pageNodes={pageNodes}
          visibleColumns={visibleColumns}
          sortColumns={sortColumns}
          onToggleSort={toggleSort}
          selectedNodeKey={selectedNodeKey}
          onSelectNode={handleSelectNode}
          checkedKeys={checkedKeys}
          onToggleChecked={toggleChecked}
          onCheckRange={handleGridCheckRange}
          onToggleAllChecked={handleToggleAllChecked}
          allChecked={allPageChecked}
          someChecked={somePageChecked}
          connectionCounts={connectionCounts}
          sourceCounts={sourceCounts}
          searchTerm={searchTerm}
          containerRef={containerRef}
        />
      )}

      <TablePagination
        currentPage={effectivePage}
        pageCount={pageCount}
        pageSize={pageSize}
        filteredCount={filteredCount}
        onPageChange={setCurrentPage}
        onPageSizeChange={setPageSize}
      />

      {/* Dialogs */}
      <MergeEntitiesDialog
        open={mergeOpen}
        onOpenChange={setMergeOpen}
        entity1={checkedNodes[0] ?? null}
        entity2={checkedNodes[1] ?? null}
        caseId={caseId ?? ""}
        onMerged={handleMerged}
      />

      <AddNodeDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        caseId={caseId ?? ""}
        onCreated={handleCreated}
      />

      <BulkEditDialog
        open={bulkEditOpen}
        onOpenChange={setBulkEditOpen}
        entityKeys={checkedArray}
        knownProperties={knownProperties}
        onComplete={handleBulkEditComplete}
      />

      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {checkedArray.length} entities?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This will move the selected entities to the recycle bin. This action can be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={confirmDelete}
              disabled={deleting}
            >
              {deleting ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
