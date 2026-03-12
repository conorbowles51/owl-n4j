import { create } from "zustand"
import type { TimelineCluster } from "../lib/timeline-utils"

interface TimelineState {
  // Filters
  selectedTypes: Set<string>
  selectedEntityKeys: Set<string>
  dateRange: { start: string | null; end: string | null }
  searchTerm: string

  // Selection
  selectedEventKey: string | null
  multiSelectedKeys: Set<string>

  // UI
  filterSidebarOpen: boolean
  visibleWindow: { start: string; end: string } | null

  // Clusters
  clusters: TimelineCluster[]
  activeClusterIndex: number
  scrollToEventKey: string | null

  // Actions — Filters
  toggleType: (type: string) => void
  selectAllTypes: (types: string[]) => void
  clearAllTypes: () => void
  toggleEntity: (key: string) => void
  setSelectedEntities: (keys: Set<string>) => void
  clearEntityFilter: () => void
  setDateRange: (range: { start: string | null; end: string | null }) => void
  setSearchTerm: (term: string) => void
  clearAllFilters: (allTypes: string[]) => void

  // Actions — Selection
  selectEvent: (key: string) => void
  multiSelectEvent: (key: string) => void
  clearSelection: () => void

  // Actions — UI
  toggleFilterSidebar: () => void
  setVisibleWindow: (window: { start: string; end: string } | null) => void

  // Actions — Clusters
  setClusters: (clusters: TimelineCluster[]) => void
  nextCluster: () => void
  prevCluster: () => void
  goToCluster: (index: number) => void

  // Actions — Scroll
  scrollToEvent: (key: string) => void
  clearScrollTarget: () => void
}

export const useTimelineStore = create<TimelineState>((set, get) => ({
  selectedTypes: new Set(),
  selectedEntityKeys: new Set(),
  dateRange: { start: null, end: null },
  searchTerm: "",

  selectedEventKey: null,
  multiSelectedKeys: new Set(),

  filterSidebarOpen: true,
  visibleWindow: null,

  clusters: [],
  activeClusterIndex: -1,
  scrollToEventKey: null,

  // Filter actions
  toggleType: (type) =>
    set((s) => {
      const next = new Set(s.selectedTypes)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return { selectedTypes: next }
    }),

  selectAllTypes: (types) => set({ selectedTypes: new Set(types) }),
  clearAllTypes: () => set({ selectedTypes: new Set() }),

  toggleEntity: (key) =>
    set((s) => {
      const next = new Set(s.selectedEntityKeys)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return { selectedEntityKeys: next }
    }),

  setSelectedEntities: (keys) => set({ selectedEntityKeys: new Set(keys) }),
  clearEntityFilter: () => set({ selectedEntityKeys: new Set() }),

  setDateRange: (range) => set({ dateRange: range }),
  setSearchTerm: (term) => set({ searchTerm: term }),

  clearAllFilters: (allTypes) =>
    set({
      selectedTypes: new Set(allTypes),
      selectedEntityKeys: new Set(),
      dateRange: { start: null, end: null },
      searchTerm: "",
    }),

  // Selection actions
  selectEvent: (key) =>
    set((s) => ({
      selectedEventKey: s.selectedEventKey === key ? null : key,
      multiSelectedKeys: new Set(),
    })),

  multiSelectEvent: (key) =>
    set((s) => {
      const next = new Set(s.multiSelectedKeys)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return {
        multiSelectedKeys: next,
        selectedEventKey: next.size > 0 ? null : s.selectedEventKey,
      }
    }),

  clearSelection: () =>
    set({ selectedEventKey: null, multiSelectedKeys: new Set() }),

  // UI actions
  toggleFilterSidebar: () =>
    set((s) => ({ filterSidebarOpen: !s.filterSidebarOpen })),

  setVisibleWindow: (window) => set({ visibleWindow: window }),

  // Cluster actions
  setClusters: (clusters) => set({ clusters, activeClusterIndex: -1 }),

  nextCluster: () => {
    const { clusters, activeClusterIndex } = get()
    if (clusters.length === 0) return
    const next = Math.min(activeClusterIndex + 1, clusters.length - 1)
    set({ activeClusterIndex: next })
    // Scroll to first event in cluster
    const cluster = clusters[next]
    if (cluster) {
      set({
        visibleWindow: { start: cluster.startDate, end: cluster.endDate },
      })
    }
  },

  prevCluster: () => {
    const { clusters, activeClusterIndex } = get()
    if (clusters.length === 0) return
    const prev = Math.max(activeClusterIndex - 1, 0)
    set({ activeClusterIndex: prev })
    const cluster = clusters[prev]
    if (cluster) {
      set({
        visibleWindow: { start: cluster.startDate, end: cluster.endDate },
      })
    }
  },

  goToCluster: (index) => {
    const { clusters } = get()
    if (index < 0 || index >= clusters.length) return
    set({ activeClusterIndex: index })
    const cluster = clusters[index]
    if (cluster) {
      set({
        visibleWindow: { start: cluster.startDate, end: cluster.endDate },
      })
    }
  },

  // Scroll actions
  scrollToEvent: (key) => set({ scrollToEventKey: key }),
  clearScrollTarget: () => set({ scrollToEventKey: null }),
}))
