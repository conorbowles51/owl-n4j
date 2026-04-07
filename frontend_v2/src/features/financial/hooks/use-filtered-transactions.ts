import { useMemo } from "react"
import type { Transaction } from "../api"
import type { SortColumn } from "../stores/financial.store"
import {
  getFinancialDateTimestamp,
  isValidFinancialDate,
} from "../lib/date-utils"

interface FilterParams {
  searchQuery: string
  selectedCategories: Set<string>
  startDate: string
  endDate: string
  entityFilter: { key: string; name: string } | null
  minAmount: string
  maxAmount: string
  sortColumns: SortColumn[]
  pageSize: number
  currentPage: number
}

interface FilteredResult {
  filteredTransactions: Transaction[]
  pageTransactions: Transaction[]
  filteredCount: number
  pageCount: number
  categoryCounts: Map<string, number>
}

function entityMatches(entity: Transaction["from_entity"], query: string): boolean {
  return !!entity.name?.toLowerCase().includes(query)
}

function matchesEntityFilter(
  tx: Transaction,
  entity: { key: string; name: string }
): boolean {
  return (
    tx.from_entity?.key === entity.key ||
    tx.to_entity?.key === entity.key ||
    tx.from_entity?.name === entity.name ||
    tx.to_entity?.name === entity.name
  )
}

function compareDateValues(a: string | null | undefined, b: string | null | undefined) {
  const aTime = getFinancialDateTimestamp(a)
  const bTime = getFinancialDateTimestamp(b)
  if (aTime == null && bTime == null) return 0
  if (aTime == null) return 1
  if (bTime == null) return -1
  return aTime - bTime
}

function compareTx(a: Transaction, b: Transaction, col: SortColumn): number {
  let cmp = 0
  switch (col.key) {
    case "date":
      cmp = compareDateValues(a.date, b.date)
      break
    case "amount":
      cmp = a.amount - b.amount
      break
    case "name":
      cmp = (a.name || "").localeCompare(b.name || "")
      break
    case "from":
      cmp = (a.from_entity?.name || "").localeCompare(b.from_entity?.name || "")
      break
    case "to":
      cmp = (a.to_entity?.name || "").localeCompare(b.to_entity?.name || "")
      break
    case "type":
      cmp = (a.type || "").localeCompare(b.type || "")
      break
    case "category":
      cmp = (a.category || "").localeCompare(b.category || "")
      break
    default:
      cmp = 0
  }
  return col.asc ? cmp : -cmp
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

  // Filter pipeline
  const filteredTransactions = useMemo(() => {
    if (!transactions) return []
    let result = transactions

    // Text search
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      result = result.filter(
        (tx) =>
          tx.name?.toLowerCase().includes(q) ||
          entityMatches(tx.from_entity, q) ||
          entityMatches(tx.to_entity, q) ||
          tx.purpose?.toLowerCase().includes(q) ||
          tx.notes?.toLowerCase().includes(q) ||
          tx.counterparty_details?.toLowerCase().includes(q)
      )
    }

    // Amount range
    if (minAmount) {
      const min = parseFloat(minAmount)
      if (!isNaN(min)) result = result.filter((tx) => Math.abs(tx.amount) >= min)
    }
    if (maxAmount) {
      const max = parseFloat(maxAmount)
      if (!isNaN(max)) result = result.filter((tx) => Math.abs(tx.amount) <= max)
    }

    // Entity filter
    if (entityFilter) {
      result = result.filter((tx) => matchesEntityFilter(tx, entityFilter))
    }

    // Date range
    if (startDate) {
      result = result.filter(
        (tx) => isValidFinancialDate(tx.date) && tx.date! >= startDate
      )
    }
    if (endDate) {
      result = result.filter(
        (tx) => isValidFinancialDate(tx.date) && tx.date! <= endDate
      )
    }

    // Category filter
    if (selectedCategories.size > 0) {
      result = result.filter((tx) =>
        selectedCategories.has(tx.category || "Uncategorized")
      )
    }

    // Sort
    if (sortColumns.length > 0) {
      result = [...result].sort((a, b) => {
        for (const col of sortColumns) {
          const cmp = compareTx(a, b, col)
          if (cmp !== 0) return cmp
        }
        return 0
      })
    }

    return result
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
    filteredTransactions,
    pageTransactions,
    filteredCount,
    pageCount,
    categoryCounts,
  }
}
