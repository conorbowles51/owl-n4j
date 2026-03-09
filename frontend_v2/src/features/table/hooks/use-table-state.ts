import { useState, useCallback, useEffect } from "react"
import type { ColumnConfig } from "../components/TableColumnConfig"

interface TableState {
  sortKey: string
  sortAsc: boolean
  columns: ColumnConfig[]
  search: string
}

const STORAGE_KEY = "owl-table-state"

const DEFAULT_COLUMNS: ColumnConfig[] = [
  { key: "label", label: "Name", visible: true },
  { key: "type", label: "Type", visible: true },
  { key: "properties", label: "Properties", visible: true },
  { key: "connections", label: "Connections", visible: true },
  { key: "confidence", label: "Confidence", visible: false },
  { key: "sources", label: "Sources", visible: false },
]

function loadState(): TableState {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored) as Partial<TableState>
      return {
        sortKey: parsed.sortKey ?? "label",
        sortAsc: parsed.sortAsc ?? true,
        columns: parsed.columns ?? DEFAULT_COLUMNS,
        search: "",
      }
    }
  } catch {
    // ignore
  }
  return {
    sortKey: "label",
    sortAsc: true,
    columns: DEFAULT_COLUMNS,
    search: "",
  }
}

export function useTableState() {
  const [state, setState] = useState<TableState>(loadState)

  useEffect(() => {
    const { search: _, ...persist } = state
    localStorage.setItem(STORAGE_KEY, JSON.stringify(persist))
  }, [state])

  const setSearch = useCallback((search: string) => {
    setState((prev) => ({ ...prev, search }))
  }, [])

  const setSort = useCallback((key: string) => {
    setState((prev) => ({
      ...prev,
      sortKey: key,
      sortAsc: prev.sortKey === key ? !prev.sortAsc : true,
    }))
  }, [])

  const setColumns = useCallback((columns: ColumnConfig[]) => {
    setState((prev) => ({ ...prev, columns }))
  }, [])

  const visibleColumns = state.columns.filter((c) => c.visible)

  return {
    ...state,
    visibleColumns,
    setSearch,
    setSort,
    setColumns,
  }
}
