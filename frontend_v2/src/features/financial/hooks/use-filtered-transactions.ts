import { useMemo } from "react"
import type { Transaction } from "../api"
import {
  applyDirectionalEntitySelections,
  filterTransactionsBase,
} from "../lib/filter-transactions"
import type { SortColumn } from "../stores/financial.store"

interface FilterParams {
  searchQuery: string
  selectedCategories: Set<string>
  startDate: string
  endDate: string
  entityFilter: { key: string; name: string } | null
  selectedFromEntities: Set<string>
  selectedToEntities: Set<string>
  minAmount: string
  maxAmount: string
  sortColumns: SortColumn[]
  pageSize: number
  currentPage: number
}

interface FilteredResult {
  baseFilteredTransactions: Transaction[]
  filteredTransactions: Transaction[]
  pageTransactions: Transaction[]
  filteredCount: number
  pageCount: number
  categoryCounts: Map<string, number>
}

export function useFilteredTransactions(
  transactions: Transaction[] | undefined,
  params: FilterParams
): FilteredResult {
  const {
    searchQuery,
    selectedCategories,
    startDate,
    endDate,
    entityFilter,
    selectedFromEntities,
    selectedToEntities,
    minAmount,
    maxAmount,
    sortColumns,
    pageSize,
    currentPage,
  } = params

  // Count categories from all transactions (pre-filter)
  const categoryCounts = useMemo(() => {
    const counts = new Map<string, number>()
    if (!transactions) return counts
    for (const tx of transactions) {
      const c = tx.category || "Uncategorized"
      counts.set(c, (counts.get(c) || 0) + 1)
    }
    return counts
  }, [transactions])

  const baseFilteredTransactions = useMemo(() => {
    return filterTransactionsBase(transactions, {
      searchQuery,
      selectedCategories,
      startDate,
      endDate,
      entityFilter,
      minAmount,
      maxAmount,
      sortColumns,
    })
  }, [
    transactions,
    searchQuery,
    minAmount,
    maxAmount,
    entityFilter,
    startDate,
    endDate,
    selectedCategories,
    sortColumns,
  ])

  const filteredTransactions = useMemo(
    () =>
      applyDirectionalEntitySelections(
        baseFilteredTransactions,
        selectedFromEntities,
        selectedToEntities
      ),
    [baseFilteredTransactions, selectedFromEntities, selectedToEntities]
  )

  // Pagination
  const filteredCount = filteredTransactions.length
  const pageCount =
    pageSize === -1 ? 1 : Math.max(1, Math.ceil(filteredCount / pageSize))

  const pageTransactions = useMemo(() => {
    if (pageSize === -1) return filteredTransactions
    const start = currentPage * pageSize
    return filteredTransactions.slice(start, start + pageSize)
  }, [filteredTransactions, pageSize, currentPage])

  return {
    baseFilteredTransactions,
    filteredTransactions,
    pageTransactions,
    filteredCount,
    pageCount,
    categoryCounts,
  }
}
