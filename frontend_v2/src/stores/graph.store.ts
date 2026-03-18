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

interface ContextMenuData {
  x: number
  y: number
  nodeKey: string
  nodeLabel: string
}

type ContextMenuState = ContextMenuData | null

interface GraphStore {
  /* Selection */
  selectedNodeKeys: Set<string>
  focusHistory: FocusEntry[]
  searchTerm: string
  filters: Record<string, boolean>
  viewSettings: GraphViewSettings

  /* Force simulation controls */
  linkDistance: number
  chargeStrength: number
  centerStrength: number
  showRelationshipLabels: boolean

  /* Node visibility */
  hiddenNodeKeys: Set<string>
  pinnedNodeKeys: Set<string>

  /* Selection mode */
  selectionMode: "click" | "drag"

  /* Subgraph / Spotlight */
  subgraphNodeKeys: Set<string>
  spotlightVisible: boolean

  /* Context menu */
  contextMenu: ContextMenuState

  /* Community overlay from analysis */
  communityMap: Map<string, number> | null

  /* Highlighted paths from shortest-path analysis */
  highlightedPaths: Set<string> | null

  /* Analysis results highlight (pagerank/betweenness top-N node keys) */
  analysisHighlight: Set<string> | null

  /* Actions: selection */
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

  /* Actions: force controls */
  setLinkDistance: (val: number) => void
  setChargeStrength: (val: number) => void
  setCenterStrength: (val: number) => void
  setShowRelationshipLabels: (val: boolean) => void

  /* Actions: node visibility */
  hideNode: (key: string) => void
  unhideNode: (key: string) => void
  unhideAll: () => void
  pinNode: (key: string) => void
  unpinNode: (key: string) => void
  togglePin: (key: string) => void

  /* Actions: selection mode */
  setSelectionMode: (mode: "click" | "drag") => void

  /* Actions: subgraph / spotlight */
  addToSubgraph: (keys: string[]) => void
  removeFromSubgraph: (keys: string[]) => void
  clearSubgraph: () => void
  toggleSpotlight: () => void
  setSpotlightVisible: (v: boolean) => void

  /* Actions: context menu */
  openContextMenu: (state: ContextMenuData) => void
  closeContextMenu: () => void

  /* Actions: analysis overlays */
  setCommunityMap: (map: Map<string, number> | null) => void
  setHighlightedPaths: (paths: Set<string> | null) => void
  setAnalysisHighlight: (keys: Set<string> | null) => void

}

export const useGraphStore = create<GraphStore>((set) => ({
  /* Defaults */
  selectedNodeKeys: new Set(),
  focusHistory: [],
  searchTerm: "",
  filters: {},
  viewSettings: { layout: "force", showLabels: true, showEdgeLabels: false },

  linkDistance: 200,
  chargeStrength: -50,
  centerStrength: 0.4,
  showRelationshipLabels: false,

  hiddenNodeKeys: new Set(),
  pinnedNodeKeys: new Set(),

  selectionMode: "click",

  subgraphNodeKeys: new Set(),
  spotlightVisible: true,

  contextMenu: null,

  communityMap: null,
  highlightedPaths: null,
  analysisHighlight: null,

  /* Selection */
  selectNodes: (keys) => set({ selectedNodeKeys: new Set(keys) }),

  addToSelection: (key) =>
    set((s) => {
      const next = new Set(s.selectedNodeKeys)
      if (next.has(key)) next.delete(key)
      else next.add(key)
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

  /* Force controls */
  setLinkDistance: (val) => set({ linkDistance: val }),
  setChargeStrength: (val) => set({ chargeStrength: val }),
  setCenterStrength: (val) => set({ centerStrength: val }),
  setShowRelationshipLabels: (val) => set({ showRelationshipLabels: val }),

  /* Node visibility */
  hideNode: (key) =>
    set((s) => {
      const next = new Set(s.hiddenNodeKeys)
      next.add(key)
      return { hiddenNodeKeys: next }
    }),
  unhideNode: (key) =>
    set((s) => {
      const next = new Set(s.hiddenNodeKeys)
      next.delete(key)
      return { hiddenNodeKeys: next }
    }),
  unhideAll: () => set({ hiddenNodeKeys: new Set() }),

  pinNode: (key) =>
    set((s) => {
      const next = new Set(s.pinnedNodeKeys)
      next.add(key)
      return { pinnedNodeKeys: next }
    }),
  unpinNode: (key) =>
    set((s) => {
      const next = new Set(s.pinnedNodeKeys)
      next.delete(key)
      return { pinnedNodeKeys: next }
    }),
  togglePin: (key) =>
    set((s) => {
      const next = new Set(s.pinnedNodeKeys)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return { pinnedNodeKeys: next }
    }),

  /* Selection mode */
  setSelectionMode: (mode) => set({ selectionMode: mode }),

  /* Subgraph / Spotlight */
  addToSubgraph: (keys) =>
    set((s) => {
      const next = new Set(s.subgraphNodeKeys)
      for (const k of keys) next.add(k)
      return { subgraphNodeKeys: next, spotlightVisible: true }
    }),
  removeFromSubgraph: (keys) =>
    set((s) => {
      const next = new Set(s.subgraphNodeKeys)
      for (const k of keys) next.delete(k)
      return { subgraphNodeKeys: next }
    }),
  clearSubgraph: () => set({ subgraphNodeKeys: new Set() }),
  toggleSpotlight: () => set((s) => ({ spotlightVisible: !s.spotlightVisible })),
  setSpotlightVisible: (v) => set({ spotlightVisible: v }),

  /* Context menu */
  openContextMenu: (state) => set({ contextMenu: state }),
  closeContextMenu: () => set({ contextMenu: null }),

  /* Analysis overlays */
  setCommunityMap: (map) => set({ communityMap: map }),
  setHighlightedPaths: (paths) => set({ highlightedPaths: paths }),
  setAnalysisHighlight: (keys) => set({ analysisHighlight: keys }),

}))
