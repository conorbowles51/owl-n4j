import { create } from "zustand"

interface FocusEntry {
  nodeKey: string
  label: string
}

interface GraphViewSettings {
  layout: "force" | "hierarchical" | "radial" | "circular"
  showLabels: boolean
  showEdgeLabels: boolean
}

interface GraphStore {
  selectedNodeKeys: Set<string>
  focusHistory: FocusEntry[]
  searchTerm: string
  filters: Record<string, boolean>
  viewSettings: GraphViewSettings

  selectNodes: (keys: string[]) => void
  addToSelection: (key: string) => void
  clearSelection: () => void
  pushFocus: (entry: FocusEntry) => void
  popFocus: () => void
  setSearchTerm: (term: string) => void
  setFilter: (key: string, value: boolean) => void
  setViewSetting: <K extends keyof GraphViewSettings>(
    key: K,
    value: GraphViewSettings[K]
  ) => void
}

export const useGraphStore = create<GraphStore>((set) => ({
  selectedNodeKeys: new Set(),
  focusHistory: [],
  searchTerm: "",
  filters: {},
  viewSettings: {
    layout: "force",
    showLabels: true,
    showEdgeLabels: false,
  },

  selectNodes: (keys) => set({ selectedNodeKeys: new Set(keys) }),

  addToSelection: (key) =>
    set((s) => {
      const next = new Set(s.selectedNodeKeys)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return { selectedNodeKeys: next }
    }),

  clearSelection: () => set({ selectedNodeKeys: new Set() }),

  pushFocus: (entry) =>
    set((s) => ({ focusHistory: [...s.focusHistory, entry] })),

  popFocus: () =>
    set((s) => ({ focusHistory: s.focusHistory.slice(0, -1) })),

  setSearchTerm: (term) => set({ searchTerm: term }),

  setFilter: (key, value) =>
    set((s) => ({ filters: { ...s.filters, [key]: value } })),

  setViewSetting: (key, value) =>
    set((s) => ({
      viewSettings: { ...s.viewSettings, [key]: value },
    })),
}))
