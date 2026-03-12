import { create } from "zustand"
import { persist } from "zustand/middleware"

export interface SortColumn {
  key: string
  asc: boolean
}

export interface RelationshipNavEntry {
  nodeKey: string
  nodeLabel: string
  nodeType: string
  relationshipTypes: string[] // e.g. ["WORKS_FOR"]
}

interface TableStoreState {
  // Filters
  searchTerm: string
  selectedTypes: Set<string>

  // Sorting
  sortColumns: SortColumn[]

  // Pagination
  pageSize: number
  currentPage: number

  // Selection (table-specific multi-select for bulk actions)
  checkedKeys: Set<string>
  lastClickedKey: string | null

  // Column config
  columnOrder: string[]

  // UI
  typeFilterOpen: boolean

  // Relationship navigation
  navigationStack: RelationshipNavEntry[]
}

interface TableStoreActions {
  setSearchTerm: (term: string) => void
  setSelectedTypes: (types: Set<string>) => void
  toggleType: (type: string) => void
  selectAllTypes: (types: string[]) => void
  clearTypes: () => void

  toggleSort: (key: string, multi?: boolean) => void
  clearSort: () => void

  setPageSize: (size: number) => void
  setCurrentPage: (page: number) => void

  toggleChecked: (key: string) => void
  setCheckedKeys: (keys: Set<string>) => void
  checkRange: (keys: string[]) => void
  clearChecked: () => void
  setLastClickedKey: (key: string | null) => void

  setColumnOrder: (order: string[]) => void
  setTypeFilterOpen: (open: boolean) => void

  pushNavigation: (entry: RelationshipNavEntry) => void
  popToIndex: (index: number) => void
  clearNavigation: () => void

  reset: () => void
}

type TableStore = TableStoreState & TableStoreActions

const initialState: TableStoreState = {
  searchTerm: "",
  selectedTypes: new Set<string>(),
  sortColumns: [{ key: "label", asc: true }],
  pageSize: 50,
  currentPage: 0,
  checkedKeys: new Set<string>(),
  lastClickedKey: null,
  columnOrder: ["label", "type", "confidence", "summary", "connections", "sources"],
  typeFilterOpen: false,
  navigationStack: [],
}

export const useTableStore = create<TableStore>()(
  persist(
    (set) => ({
      ...initialState,

      setSearchTerm: (term) => set({ searchTerm: term, currentPage: 0 }),
      setSelectedTypes: (types) => set({ selectedTypes: types, currentPage: 0 }),
      toggleType: (type) =>
        set((s) => {
          const next = new Set(s.selectedTypes)
          if (next.has(type)) next.delete(type)
          else next.add(type)
          return { selectedTypes: next, currentPage: 0 }
        }),
      selectAllTypes: (types) => set({ selectedTypes: new Set(types), currentPage: 0 }),
      clearTypes: () => set({ selectedTypes: new Set<string>(), currentPage: 0 }),

      toggleSort: (key, multi) =>
        set((s) => {
          if (multi) {
            const idx = s.sortColumns.findIndex((c) => c.key === key)
            if (idx >= 0) {
              const updated = [...s.sortColumns]
              if (updated[idx].asc) {
                updated[idx] = { key, asc: false }
              } else {
                updated.splice(idx, 1)
              }
              return { sortColumns: updated }
            }
            return { sortColumns: [...s.sortColumns, { key, asc: true }] }
          }
          const existing = s.sortColumns[0]
          if (existing?.key === key) {
            if (existing.asc) return { sortColumns: [{ key, asc: false }] }
            return { sortColumns: [] }
          }
          return { sortColumns: [{ key, asc: true }] }
        }),
      clearSort: () => set({ sortColumns: [{ key: "label", asc: true }] }),

      setPageSize: (size) => set({ pageSize: size, currentPage: 0 }),
      setCurrentPage: (page) => set({ currentPage: page }),

      toggleChecked: (key) =>
        set((s) => {
          const next = new Set(s.checkedKeys)
          if (next.has(key)) next.delete(key)
          else next.add(key)
          return { checkedKeys: next, lastClickedKey: key }
        }),
      setCheckedKeys: (keys) => set({ checkedKeys: keys }),
      checkRange: (keys) =>
        set((s) => {
          const next = new Set(s.checkedKeys)
          for (const k of keys) next.add(k)
          return { checkedKeys: next }
        }),
      clearChecked: () => set({ checkedKeys: new Set<string>(), lastClickedKey: null }),
      setLastClickedKey: (key) => set({ lastClickedKey: key }),

      setColumnOrder: (order) => set({ columnOrder: order }),
      setTypeFilterOpen: (open) => set({ typeFilterOpen: open }),

      pushNavigation: (entry) =>
        set((s) => ({
          navigationStack: [...s.navigationStack, entry],
          currentPage: 0,
          checkedKeys: new Set<string>(),
          lastClickedKey: null,
        })),
      popToIndex: (index) =>
        set((s) => ({
          navigationStack: index < 0 ? [] : s.navigationStack.slice(0, index + 1),
          currentPage: 0,
          checkedKeys: new Set<string>(),
          lastClickedKey: null,
        })),
      clearNavigation: () =>
        set({
          navigationStack: [],
          currentPage: 0,
          checkedKeys: new Set<string>(),
          lastClickedKey: null,
        }),

      reset: () => set(initialState),
    }),
    {
      name: "owl-table-store",
      partialize: (state) => ({
        sortColumns: state.sortColumns,
        pageSize: state.pageSize,
        columnOrder: state.columnOrder,
      }),
      // Sets need special serialization handling
      storage: {
        getItem: (name) => {
          const str = localStorage.getItem(name)
          return str ? JSON.parse(str) : null
        },
        setItem: (name, value) => {
          localStorage.setItem(name, JSON.stringify(value))
        },
        removeItem: (name) => localStorage.removeItem(name),
      },
    }
  )
)
