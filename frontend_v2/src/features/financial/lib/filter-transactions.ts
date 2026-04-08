import type { Transaction } from "../api"
import type { SortColumn } from "../stores/financial.store"
import {
  getFinancialDateTimestamp,
  isValidFinancialDate,
} from "./date-utils"

export interface BaseFilterParams {
  searchQuery: string
  selectedCategories: Set<string>
  startDate: string
  endDate: string
  entityFilter: { key: string; name: string } | null
  minAmount: string
  maxAmount: string
  sortColumns: SortColumn[]
}

export interface EntityFlowRow {
  key: string
  name: string
  count: number
  totalAmount: number
}

type EntitySide = "from" | "to"

function matchesEntityText(value: string | null | undefined, query: string): boolean {
  return !!value?.toLowerCase().includes(query)
}

export function getEntitySelectionValue(
  entity: Transaction["from_entity"] | Transaction["to_entity"]
): string | null {
  return entity?.key || entity?.name || null
}

export function matchesEntityFilter(
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

export function compareTransactions(a: Transaction, b: Transaction, col: SortColumn): number {
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

export function transactionMatchesSearch(tx: Transaction, query: string): boolean {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return true

  return [
    tx.name,
    tx.summary,
    tx.purpose,
    tx.notes,
    tx.counterparty_details,
    tx.category,
    tx.from_entity?.name,
    tx.to_entity?.name,
  ].some((value) => matchesEntityText(value, normalized))
}

export function filterTransactionsBase(
  transactions: Transaction[] | undefined,
  params: BaseFilterParams
): Transaction[] {
  if (!transactions) return []

  const {
    searchQuery,
    selectedCategories,
    startDate,
    endDate,
    entityFilter,
    minAmount,
    maxAmount,
    sortColumns,
  } = params

  let result = [...transactions]

  if (searchQuery) {
    result = result.filter((tx) => transactionMatchesSearch(tx, searchQuery))
  }

  if (minAmount) {
    const min = parseFloat(minAmount)
    if (!Number.isNaN(min)) {
      result = result.filter((tx) => Math.abs(tx.amount) >= min)
    }
  }

  if (maxAmount) {
    const max = parseFloat(maxAmount)
    if (!Number.isNaN(max)) {
      result = result.filter((tx) => Math.abs(tx.amount) <= max)
    }
  }

  if (entityFilter) {
    result = result.filter((tx) => matchesEntityFilter(tx, entityFilter))
  }

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

  if (selectedCategories.size > 0) {
    result = result.filter((tx) =>
      selectedCategories.has(tx.category || "Uncategorized")
    )
  }

  if (sortColumns.length > 0) {
    result.sort((a, b) => {
      for (const col of sortColumns) {
        const cmp = compareTransactions(a, b, col)
        if (cmp !== 0) return cmp
      }
      return 0
    })
  }

  return result
}

export function applyDirectionalEntitySelections(
  transactions: Transaction[],
  fromSelections: Set<string>,
  toSelections: Set<string>
): Transaction[] {
  if (fromSelections.size === 0 && toSelections.size === 0) {
    return transactions
  }

  return transactions.filter((tx) => {
    const fromValue = getEntitySelectionValue(tx.from_entity)
    const toValue = getEntitySelectionValue(tx.to_entity)

    if (fromSelections.size > 0 && (!fromValue || !fromSelections.has(fromValue))) {
      return false
    }

    if (toSelections.size > 0 && (!toValue || !toSelections.has(toValue))) {
      return false
    }

    return true
  })
}

export function buildEntityFlowRows(
  transactions: Transaction[],
  side: EntitySide,
  counterpartSelections: Set<string>
): EntityFlowRow[] {
  const counterSide: EntitySide = side === "from" ? "to" : "from"
  const grouped = new Map<string, EntityFlowRow>()

  for (const tx of transactions) {
    const entity = side === "from" ? tx.from_entity : tx.to_entity
    const counterpart = counterSide === "from" ? tx.from_entity : tx.to_entity
    const counterpartValue = getEntitySelectionValue(counterpart)

    if (
      counterpartSelections.size > 0 &&
      (!counterpartValue || !counterpartSelections.has(counterpartValue))
    ) {
      continue
    }

    const value = getEntitySelectionValue(entity)
    const name = entity?.name || value
    if (!value || !name) continue

    const existing = grouped.get(value)
    if (existing) {
      existing.count += 1
      existing.totalAmount += Math.abs(tx.amount)
      continue
    }

    grouped.set(value, {
      key: value,
      name,
      count: 1,
      totalAmount: Math.abs(tx.amount),
    })
  }

  return [...grouped.values()].sort((a, b) => {
    if (b.totalAmount !== a.totalAmount) {
      return b.totalAmount - a.totalAmount
    }
    return a.name.localeCompare(b.name)
  })
}
