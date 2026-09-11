import { create } from "zustand"
import { persist } from "zustand/middleware"
import type { FinancialDatasetMode } from "../api"

export interface SortColumn {
  key: string
  asc: boolean
}

/**
 * The tab in front of you on the financial page, and nothing wider than that.
 *
 * `ledger`, `quarantine`, `runs` and `decisions` read Postgres: the ledger
 * itself, the rows held out of its totals, the record of every attempt to load
 * evidence into it, and the record of what people decided about that evidence
 * afterwards. The other three read the Neo4j graph. The two stores are written
 * independently and can disagree, so which one is on screen is a fact about
 * what you are looking at, not a presentation choice. The four Postgres tabs
 * are kept next to each other in the strip for that reason, and the order below
 * is the order they appear in.
 *
 * `quarantine` sits directly after `ledger` because the two are one read
 * against two populations: what a case's totals count, and what they leave out.
 * A person who has just read a total is one tab away from what the total
 * excludes.
 *
 * `runs` is the word the backend model, the endpoint, the hook and the query
 * key all use, so it is the word kept here. The tab is labelled "Attempts" on
 * screen, which is the word the notice and the run copy already use in front of
 * a reader.
 *
 * `decisions` sits last of the four because it is the only one that is not a
 * view of the ledger's current contents. The first three each answer "what does
 * the case hold now, and what was left out"; this one answers "who moved it,
 * and on what grounds", and it outlives its subjects -- a decision to delete a
 * duplicate is recorded before the thing it is about stops existing.
 *
 * Nothing here is persisted: `partialize` omits `mainView` and `merge` deletes
 * any stored value, so a member can be added or removed without a migration and
 * a page always opens on the ledger.
 */
export type FinancialMainView =
  | "findings"
  | "patterns"
  | "case-context"
  | "ledger"
  | "statements"
  | "quarantine"
  | "runs"
  | "decisions"
  | "transactions"
  | "counterparties"
  | "trends"
  | "tracing"
  | "transfers"
  | "posting-graph"
export type ChartGroupingOption = "auto" | "daily" | "weekly" | "monthly"

interface FinancialStoreState {
  // Filters
  mode: FinancialDatasetMode
  searchQuery: string
  selectedTypes: Set<string>
  selectedCategories: Set<string>
  startDate: string
  endDate: string
  entityFilter: { key: string; name: string } | null
  minAmount: string
  maxAmount: string

  // Sort
  sortColumns: SortColumn[]

  // Pagination
  pageSize: number
  currentPage: number

  // Selection
  checkedKeys: Set<string>
  lastClickedKey: string | null

  // UI
  filterPanelOpen: boolean
  mainView: FinancialMainView
  chartGrouping: ChartGroupingOption
  expandedRowKeys: Set<string>
}

interface FinancialStoreActions {
  setSearchQuery: (query: string) => void
  setMode: (mode: FinancialDatasetMode) => void

  setSelectedTypes: (types: Set<string>) => void
  toggleType: (type: string) => void
  selectAllTypes: (types: string[]) => void
  clearTypes: () => void

  setSelectedCategories: (categories: Set<string>) => void
  toggleCategory: (category: string) => void
  selectAllCategories: (categories: string[]) => void
  clearCategories: () => void

  setStartDate: (date: string) => void
  setEndDate: (date: string) => void
  setEntityFilter: (entity: { key: string; name: string } | null) => void
  setMinAmount: (amount: string) => void
  setMaxAmount: (amount: string) => void
  resetFilters: () => void

  toggleSort: (key: string, multi?: boolean) => void
  clearSort: () => void

  setPageSize: (size: number) => void
  setCurrentPage: (page: number) => void

  toggleChecked: (key: string) => void
  setCheckedKeys: (keys: Set<string>) => void
  checkRange: (keys: string[]) => void
  clearChecked: () => void
  setLastClickedKey: (key: string | null) => void

  setFilterPanelOpen: (open: boolean) => void
  setMainView: (view: FinancialMainView) => void
  setChartGrouping: (grouping: ChartGroupingOption) => void
  toggleExpandedRow: (key: string) => void

  reset: () => void
}

type FinancialStore = FinancialStoreState & FinancialStoreActions

const initialState: FinancialStoreState = {
  mode: "transactions",
  searchQuery: "",
  selectedTypes: new Set<string>(),
  selectedCategories: new Set<string>(),
  startDate: "",
  endDate: "",
  entityFilter: null,
  minAmount: "",
  maxAmount: "",
  sortColumns: [{ key: "date", asc: false }],
  pageSize: 50,
  currentPage: 0,
  checkedKeys: new Set<string>(),
  lastClickedKey: null,
  filterPanelOpen: true,
  mainView: "transactions",
  chartGrouping: "auto",
  expandedRowKeys: new Set<string>(),
}

export const useFinancialStore = create<FinancialStore>()(
  persist(
    (set) => ({
      ...initialState,

      setMode: (mode) =>
        set({
          mode,
          currentPage: 0,
          checkedKeys: new Set<string>(),
          lastClickedKey: null,
          expandedRowKeys: new Set<string>(),
        }),
      setSearchQuery: (query) => set({ searchQuery: query, currentPage: 0 }),

      setSelectedTypes: (types) =>
        set({ selectedTypes: types, currentPage: 0 }),
      toggleType: (type) =>
        set((s) => {
          const next = new Set(s.selectedTypes)
          if (next.has(type)) next.delete(type)
          else next.add(type)
          return { selectedTypes: next, currentPage: 0 }
        }),
      selectAllTypes: (types) =>
        set({ selectedTypes: new Set(types), currentPage: 0 }),
      clearTypes: () =>
        set({ selectedTypes: new Set<string>(), currentPage: 0 }),

      setSelectedCategories: (categories) =>
        set({ selectedCategories: categories, currentPage: 0 }),
      toggleCategory: (category) =>
        set((s) => {
          const next = new Set(s.selectedCategories)
          if (next.has(category)) next.delete(category)
          else next.add(category)
          return { selectedCategories: next, currentPage: 0 }
        }),
      selectAllCategories: (categories) =>
        set({ selectedCategories: new Set(categories), currentPage: 0 }),
      clearCategories: () =>
        set({ selectedCategories: new Set<string>(), currentPage: 0 }),

      setStartDate: (date) => set({ startDate: date, currentPage: 0 }),
      setEndDate: (date) => set({ endDate: date, currentPage: 0 }),
      setEntityFilter: (entity) =>
        set({ entityFilter: entity, currentPage: 0 }),
      setMinAmount: (amount) => set({ minAmount: amount, currentPage: 0 }),
      setMaxAmount: (amount) => set({ maxAmount: amount, currentPage: 0 }),
      resetFilters: () =>
        set({
          searchQuery: "",
          selectedTypes: new Set<string>(),
          selectedCategories: new Set<string>(),
          startDate: "",
          endDate: "",
          entityFilter: null,
          minAmount: "",
          maxAmount: "",
          currentPage: 0,
        }),

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
      clearSort: () => set({ sortColumns: [{ key: "date", asc: false }] }),

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
      clearChecked: () =>
        set({ checkedKeys: new Set<string>(), lastClickedKey: null }),
      setLastClickedKey: (key) => set({ lastClickedKey: key }),

      setFilterPanelOpen: (open) => set({ filterPanelOpen: open }),
      setMainView: (mainView) => set({ mainView }),
      setChartGrouping: (chartGrouping) => set({ chartGrouping }),
      toggleExpandedRow: (key) =>
        set((s) => {
          const next = new Set(s.expandedRowKeys)
          if (next.has(key)) next.delete(key)
          else next.add(key)
          return { expandedRowKeys: next }
        }),

      reset: () => set(initialState),
    }),
    {
      name: "owl-financial-store",
      /**
       * `mainView` is deliberately not written. The financial page opens on
       * the ledger every time, so which tab you were last on is not carried
       * between visits.
       */
      partialize: (state) => ({
        sortColumns: state.sortColumns,
        pageSize: state.pageSize,
        filterPanelOpen: state.filterPanelOpen,
        chartGrouping: state.chartGrouping,
      }),
      // Old saved intelligence views must not hide newly imported statements.
      // Keep display preferences, but open a fresh visit on transactions.
      merge: (persisted, current) => {
        const stored = { ...(persisted as Partial<FinancialStoreState> | null) }
        delete stored.mainView
        delete stored.mode
        return { ...current, ...stored }
      },
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
