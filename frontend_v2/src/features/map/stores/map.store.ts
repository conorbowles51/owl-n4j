import { create } from "zustand"

interface MapStore {
  /* Selection */
  selectedLocationKey: string | null

  /* Proximity analysis */
  proximityMode: boolean
  proximityAnchorKey: string | null
  proximityRadius: number

  /* Layer toggles */
  showHeatmap: boolean

  /* Entity type filter */
  hiddenTypes: Set<string>

  /* Confidence filter */
  hiddenConfidenceTiers: Set<string>
  needsReviewMode: boolean

  /* Heatmap tuning */
  heatmapRadius: number
  heatmapIntensity: number

  /* Programmatic navigation */
  pendingFlyTo: { longitude: number; latitude: number; zoom?: number } | null
  pendingZoomDelta: number | null
  pendingFitBounds: boolean

  /* Actions */
  selectLocation: (key: string | null) => void
  setProximityAnchor: (key: string | null) => void
  setProximityRadius: (radius: number) => void
  toggleProximityMode: () => void
  toggleHeatmap: () => void
  toggleType: (type: string) => void
  setHiddenTypes: (types: Set<string>) => void
  toggleConfidenceTier: (tier: string) => void
  clearConfidenceFilter: () => void
  toggleNeedsReviewMode: () => void
  setHeatmapRadius: (radius: number) => void
  setHeatmapIntensity: (intensity: number) => void
  flyTo: (coords: { longitude: number; latitude: number; zoom?: number }) => void
  clearFlyTo: () => void
  zoomIn: () => void
  zoomOut: () => void
  clearZoomDelta: () => void
  fitBounds: () => void
  clearFitBounds: () => void
  reset: () => void
}

export const useMapStore = create<MapStore>()((set) => ({
  selectedLocationKey: null,
  proximityMode: false,
  proximityAnchorKey: null,
  proximityRadius: 5,
  showHeatmap: false,
  hiddenTypes: new Set(),
  hiddenConfidenceTiers: new Set(),
  needsReviewMode: false,
  heatmapRadius: 30,
  heatmapIntensity: 0.6,
  pendingFlyTo: null,
  pendingZoomDelta: null,
  pendingFitBounds: false,

  selectLocation: (key) => set({ selectedLocationKey: key }),
  setProximityAnchor: (key) =>
    set({ proximityAnchorKey: key, proximityMode: key !== null }),
  setProximityRadius: (radius) => set({ proximityRadius: radius }),
  toggleProximityMode: () =>
    set((s) => {
      if (s.proximityAnchorKey) {
        return { proximityMode: false, proximityAnchorKey: null }
      }
      return { proximityMode: !s.proximityMode }
    }),
  toggleHeatmap: () => set((s) => ({ showHeatmap: !s.showHeatmap })),
  toggleType: (type) =>
    set((s) => {
      const next = new Set(s.hiddenTypes)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return { hiddenTypes: next }
    }),
  setHiddenTypes: (types) => set({ hiddenTypes: types }),
  toggleConfidenceTier: (tier) =>
    set((s) => {
      const next = new Set(s.hiddenConfidenceTiers)
      if (next.has(tier)) next.delete(tier)
      else next.add(tier)
      // A per-tier confidence filter replaces needs-review mode
      return { hiddenConfidenceTiers: next, needsReviewMode: false }
    }),
  clearConfidenceFilter: () =>
    set({ hiddenConfidenceTiers: new Set(), needsReviewMode: false }),
  toggleNeedsReviewMode: () =>
    set((s) => ({
      needsReviewMode: !s.needsReviewMode,
      // Needs-review mode supersedes any per-tier filter
      hiddenConfidenceTiers: new Set(),
    })),
  setHeatmapRadius: (radius) => set({ heatmapRadius: radius }),
  setHeatmapIntensity: (intensity) => set({ heatmapIntensity: intensity }),
  flyTo: (coords) => set({ pendingFlyTo: coords }),
  clearFlyTo: () => set({ pendingFlyTo: null }),
  zoomIn: () => set({ pendingZoomDelta: 1 }),
  zoomOut: () => set({ pendingZoomDelta: -1 }),
  clearZoomDelta: () => set({ pendingZoomDelta: null }),
  fitBounds: () => set({ pendingFitBounds: true }),
  clearFitBounds: () => set({ pendingFitBounds: false }),
  reset: () =>
    set({
      selectedLocationKey: null,
      proximityMode: false,
      proximityAnchorKey: null,
      proximityRadius: 5,
      showHeatmap: false,
      hiddenTypes: new Set(),
      hiddenConfidenceTiers: new Set(),
      needsReviewMode: false,
      pendingFlyTo: null,
      pendingZoomDelta: null,
      pendingFitBounds: false,
    }),
}))
