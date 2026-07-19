import { create } from "zustand"
import type { LocationSpecificity } from "@/lib/location-confidence"
import { closeRing, type LngLatPoint } from "../lib/geometry"

export interface BoundingShape {
  id: string
  coordinates: LngLatPoint[]
}

export type DrawTool = "box" | "polygon"

interface MapStore {
  /* Selection */
  selectedLocationKey: string | null

  /* Proximity analysis */
  proximityMode: boolean
  proximityAnchorKey: string | null
  proximityRadius: number

  /* Bounding shape filter */
  drawMode: boolean
  drawTool: DrawTool
  drawingPoints: LngLatPoint[]
  draftBoundingShapes: BoundingShape[]
  boundingShapes: BoundingShape[]

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
  toggleDrawMode: () => void
  setDrawTool: (tool: DrawTool) => void
  setDrawingPoints: (points: LngLatPoint[]) => void
  addDrawingPoint: (point: LngLatPoint) => void
  undoLastDrawingPoint: () => void
  finishDraftShape: (points?: LngLatPoint[]) => void
  finishDrawingShape: () => void
  cancelDrawingShape: () => void
  applyBoundingShapeFilter: () => void
  discardBoundingShapeDraft: () => void
  removeDraftBoundingShape: (id: string) => void
  clearDraftBoundingShapes: () => void
  removeBoundingShape: (id: string) => void
  clearBoundingShapes: () => void
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
  flyTo: (coords: {
    longitude: number
    latitude: number
    zoom?: number
  }) => void
  clearFlyTo: () => void
  zoomIn: () => void
  zoomOut: () => void
  clearZoomDelta: () => void
  fitBounds: () => void
  clearFitBounds: () => void
  reset: () => void
}

function createBoundingShape(points: LngLatPoint[]) {
  if (points.length < 3) return null
  return {
    id: globalThis.crypto?.randomUUID?.() ?? `shape-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    coordinates: closeRing(points),
  } satisfies BoundingShape
}

export const useMapStore = create<MapStore>()((set) => ({
  selectedLocationKey: null,
  proximityMode: false,
  proximityAnchorKey: null,
  proximityRadius: 5,
  drawMode: false,
  drawTool: "box",
  drawingPoints: [],
  draftBoundingShapes: [],
  boundingShapes: [],
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
    set({
      proximityAnchorKey: key,
      proximityMode: key !== null,
      ...(key ? { drawMode: false, drawingPoints: [] } : {}),
    }),
  setProximityRadius: (radius) => set({ proximityRadius: radius }),
  toggleProximityMode: () =>
    set((s) => {
      if (s.proximityAnchorKey) {
        return { proximityMode: false, proximityAnchorKey: null }
      }
      const proximityMode = !s.proximityMode
      return {
        proximityMode,
        ...(proximityMode ? { drawMode: false, drawingPoints: [] } : {}),
      }
    }),
  toggleDrawMode: () =>
    set((s) => {
      const drawMode = !s.drawMode
      // Leaving draw mode with a completable in-progress shape finishes it
      // into the pending list — "Stop drawing" must never silently discard
      // work the user can see on the map.
      const finished = drawMode ? null : createBoundingShape(s.drawingPoints)
      return {
        drawMode,
        drawingPoints: [],
        ...(finished
          ? { draftBoundingShapes: [...s.draftBoundingShapes, finished] }
          : {}),
        ...(drawMode ? { proximityMode: false, proximityAnchorKey: null } : {}),
      }
    }),
  setDrawTool: (tool) =>
    set((s) => {
      if (tool === s.drawTool) return {}
      // Switching tools mid-draw also finishes a completable shape rather
      // than dropping it.
      const finished = createBoundingShape(s.drawingPoints)
      return {
        drawTool: tool,
        drawingPoints: [],
        ...(finished
          ? { draftBoundingShapes: [...s.draftBoundingShapes, finished] }
          : {}),
      }
    }),
  setDrawingPoints: (points) => set({ drawingPoints: points }),
  addDrawingPoint: (point) =>
    set((s) => ({ drawingPoints: [...s.drawingPoints, point] })),
  undoLastDrawingPoint: () =>
    set((s) => ({ drawingPoints: s.drawingPoints.slice(0, -1) })),
  finishDraftShape: (points) =>
    set((s) => {
      const shape = createBoundingShape(points ?? s.drawingPoints)
      if (!shape) return {}
      return {
        drawingPoints: [],
        draftBoundingShapes: [...s.draftBoundingShapes, shape],
      }
    }),
  finishDrawingShape: () =>
    set((s) => {
      const shape = createBoundingShape(s.drawingPoints)
      if (!shape) return {}
      return {
        drawingPoints: [],
        draftBoundingShapes: [...s.draftBoundingShapes, shape],
      }
    }),
  cancelDrawingShape: () => set({ drawingPoints: [] }),
  applyBoundingShapeFilter: () =>
    set((s) => {
      if (s.draftBoundingShapes.length === 0) return { drawingPoints: [] }
      return {
        drawingPoints: [],
        boundingShapes: [...s.boundingShapes, ...s.draftBoundingShapes],
        draftBoundingShapes: [],
      }
    }),
  discardBoundingShapeDraft: () =>
    set({ drawingPoints: [], draftBoundingShapes: [] }),
  removeDraftBoundingShape: (id) =>
    set((s) => ({
      draftBoundingShapes: s.draftBoundingShapes.filter(
        (shape) => shape.id !== id
      ),
    })),
  clearDraftBoundingShapes: () => set({ draftBoundingShapes: [] }),
  removeBoundingShape: (id) =>
    set((s) => ({
      boundingShapes: s.boundingShapes.filter((shape) => shape.id !== id),
    })),
  clearBoundingShapes: () => set({ boundingShapes: [] }),
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
      drawMode: false,
      drawTool: "box",
      drawingPoints: [],
      draftBoundingShapes: [],
      boundingShapes: [],
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
