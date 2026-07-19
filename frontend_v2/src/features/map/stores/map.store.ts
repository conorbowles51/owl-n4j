import { create } from "zustand"
import type { LocationSpecificity } from "@/lib/location-confidence"

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

  /* Confidence threshold filter (0–100%, null = off) */
  confidenceThreshold: number | null
  confidenceDirection: "above" | "below"

  /* Specificity threshold filter (null = off) */
  specificityThreshold: LocationSpecificity | null
  specificityDirection: "at_least" | "at_most"

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
  setConfidenceThreshold: (threshold: number | null) => void
  setConfidenceDirection: (direction: "above" | "below") => void
  setSpecificityThreshold: (threshold: LocationSpecificity | null) => void
  setSpecificityDirection: (direction: "at_least" | "at_most") => void
  clearLocationFilters: () => void
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
  confidenceThreshold: null,
  confidenceDirection: "above",
  specificityThreshold: null,
  specificityDirection: "at_least",
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
  // Adjusting a threshold filter replaces needs-review mode
  setConfidenceThreshold: (threshold) =>
    set({ confidenceThreshold: threshold, needsReviewMode: false }),
  setConfidenceDirection: (direction) =>
    set({ confidenceDirection: direction, needsReviewMode: false }),
  setSpecificityThreshold: (threshold) =>
    set({ specificityThreshold: threshold, needsReviewMode: false }),
  setSpecificityDirection: (direction) =>
    set({ specificityDirection: direction, needsReviewMode: false }),
  clearLocationFilters: () =>
    set({
      confidenceThreshold: null,
      specificityThreshold: null,
      needsReviewMode: false,
    }),
  toggleNeedsReviewMode: () =>
    set((s) => ({
      needsReviewMode: !s.needsReviewMode,
      // Needs-review mode supersedes the threshold filters
      confidenceThreshold: null,
      specificityThreshold: null,
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
      confidenceThreshold: null,
      confidenceDirection: "above",
      specificityThreshold: null,
      specificityDirection: "at_least",
      needsReviewMode: false,
      pendingFlyTo: null,
      pendingZoomDelta: null,
      pendingFitBounds: false,
    }),
}))
