import { useState } from "react"
import {
  BoxSelect,
  Check,
  Crosshair,
  Layers,
  ListChecks,
  Pencil,
  ShieldCheck,
  Trash2,
  Undo2,
  Waypoints,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { useMapStore } from "../stores/map.store"
import { useMapReviewQueue, type MapLocation } from "../hooks/use-map-data"
import {
  LOCATION_SPECIFICITY_LEVELS,
  LOCATION_SPECIFICITY_LABELS,
  needsReview,
  type LocationSpecificity,
} from "@/lib/location-confidence"
import { getVisibleLocations } from "../lib/visible-locations"

interface MapToolbarProps {
  caseId: string
  locations: MapLocation[]
}

function DirectionToggle<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}) {
  return (
    <div className="flex rounded-md border border-border p-0.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`flex-1 rounded px-2 py-0.5 text-[10px] font-medium ${
            value === opt.value
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-muted"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

export function MapToolbar({ caseId, locations }: MapToolbarProps) {
  const [areasOpen, setAreasOpen] = useState(false)
  const showHeatmap = useMapStore((s) => s.showHeatmap)
  const toggleHeatmap = useMapStore((s) => s.toggleHeatmap)
  const proximityMode = useMapStore((s) => s.proximityMode)
  const proximityAnchorKey = useMapStore((s) => s.proximityAnchorKey)
  const toggleProximityMode = useMapStore((s) => s.toggleProximityMode)
  const drawMode = useMapStore((s) => s.drawMode)
  const drawTool = useMapStore((s) => s.drawTool)
  const drawingPoints = useMapStore((s) => s.drawingPoints)
  const draftBoundingShapes = useMapStore((s) => s.draftBoundingShapes)
  const boundingShapes = useMapStore((s) => s.boundingShapes)
  const toggleDrawMode = useMapStore((s) => s.toggleDrawMode)
  const setDrawTool = useMapStore((s) => s.setDrawTool)
  const undoLastDrawingPoint = useMapStore((s) => s.undoLastDrawingPoint)
  const finishDrawingShape = useMapStore((s) => s.finishDrawingShape)
  const cancelDrawingShape = useMapStore((s) => s.cancelDrawingShape)
  const applyBoundingShapeFilter = useMapStore(
    (s) => s.applyBoundingShapeFilter
  )
  const discardBoundingShapeDraft = useMapStore(
    (s) => s.discardBoundingShapeDraft
  )
  const removeDraftBoundingShape = useMapStore(
    (s) => s.removeDraftBoundingShape
  )
  const removeBoundingShape = useMapStore((s) => s.removeBoundingShape)
  const clearBoundingShapes = useMapStore((s) => s.clearBoundingShapes)
  const hiddenTypes = useMapStore((s) => s.hiddenTypes)
  const confidenceThreshold = useMapStore((s) => s.confidenceThreshold)
  const confidenceDirection = useMapStore((s) => s.confidenceDirection)
  const specificityThreshold = useMapStore((s) => s.specificityThreshold)
  const specificityDirection = useMapStore((s) => s.specificityDirection)
  const setConfidenceThreshold = useMapStore((s) => s.setConfidenceThreshold)
  const setConfidenceDirection = useMapStore((s) => s.setConfidenceDirection)
  const setSpecificityThreshold = useMapStore((s) => s.setSpecificityThreshold)
  const setSpecificityDirection = useMapStore((s) => s.setSpecificityDirection)
  const clearLocationFilters = useMapStore((s) => s.clearLocationFilters)
  const needsReviewMode = useMapStore((s) => s.needsReviewMode)
  const toggleNeedsReviewMode = useMapStore((s) => s.toggleNeedsReviewMode)

  const { data: flaggedQueue } = useMapReviewQueue(caseId)

  // Review queue = low-confidence pins + flagged geocodes with no pin
  const reviewPinCount = locations.filter(needsReview).length
  const flaggedReviewCount = (flaggedQueue ?? []).filter(needsReview).length
  const reviewCount = reviewPinCount + flaggedReviewCount

  const filters = {
    confidenceThreshold,
    confidenceDirection,
    specificityThreshold,
    specificityDirection,
  }
  const confidenceFilterActive =
    confidenceThreshold !== null || specificityThreshold !== null
  const shapeFilterActive = boundingShapes.length > 0
  const draftShapeActive = draftBoundingShapes.length > 0
  const visibleMapLocations = getVisibleLocations(locations, {
    hiddenTypes,
    ...filters,
    needsReviewMode,
    boundingShapes,
  })
  const visibleCount = visibleMapLocations.length
  const filterSummary = [
    confidenceThreshold !== null
      ? `confidence ${confidenceDirection === "above" ? "≥" : "≤"} ${confidenceThreshold}%`
      : null,
    specificityThreshold !== null
      ? `specificity ${specificityDirection === "at_least" ? "at least" : "at most"} ${LOCATION_SPECIFICITY_LABELS[specificityThreshold]}`
      : null,
  ]
    .filter(Boolean)
    .join(", ")
  const activeFilterLabels = [
    needsReviewMode ? "needs review" : null,
    confidenceFilterActive ? filterSummary : null,
    shapeFilterActive
      ? `${boundingShapes.length} area${boundingShapes.length !== 1 ? "s" : ""}`
      : null,
  ].filter(Boolean)

  const clearActiveFilters = () => {
    clearLocationFilters()
    clearBoundingShapes()
  }

  return (
    <>
      <div className="flex items-center gap-1.5 border-b border-border bg-card px-3 py-1.5">
        {/* Layer toggles */}
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="sm" className="h-7 text-xs">
              <Layers className="mr-1 size-3.5" />
              Layers
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-44 p-1">
            <button
              onClick={toggleHeatmap}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
            >
              <span
                aria-hidden="true"
                className={`size-2.5 shrink-0 rounded-full ${
                  showHeatmap ? "bg-primary" : "border border-input"
                }`}
              />
              Heatmap
            </button>
          </PopoverContent>
        </Popover>

        {/* Confidence + specificity filter */}
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant={confidenceFilterActive ? "secondary" : "ghost"}
              size="sm"
              className="h-7 text-xs"
            >
              <ShieldCheck className="mr-1 size-3.5" />
              Confidence
              {confidenceFilterActive && (
                <Badge variant="amber" className="ml-1 text-[9px]">
                  {confidenceThreshold !== null
                    ? `${confidenceDirection === "above" ? "≥" : "≤"} ${confidenceThreshold}%`
                    : "Filtered"}
                </Badge>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-64 p-3">
            <div className="flex flex-col gap-3">
              {/* Confidence threshold */}
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Confidence threshold
                  </span>
                  {confidenceThreshold !== null && (
                    <button
                      onClick={() => setConfidenceThreshold(null)}
                      className="text-[10px] text-muted-foreground hover:text-foreground"
                    >
                      Off
                    </button>
                  )}
                </div>
                <DirectionToggle
                  value={confidenceDirection}
                  options={[
                    { value: "above", label: "Above" },
                    { value: "below", label: "Below" },
                  ]}
                  onChange={setConfidenceDirection}
                />
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min={0}
                    max={100}
                    step={1}
                    value={confidenceThreshold ?? 50}
                    onChange={(e) =>
                      setConfidenceThreshold(Number(e.target.value))
                    }
                    className="flex-1 accent-primary"
                  />
                  <div className="flex items-center gap-0.5">
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={confidenceThreshold ?? ""}
                      placeholder="--"
                      onChange={(e) => {
                        const value = e.target.value
                        if (value === "") {
                          setConfidenceThreshold(null)
                          return
                        }
                        const parsed = Number(value)
                        if (Number.isFinite(parsed)) {
                          setConfidenceThreshold(
                            Math.min(100, Math.max(0, Math.round(parsed)))
                          )
                        }
                      }}
                      className="w-12 rounded border border-border bg-background px-1 py-0.5 text-right text-xs text-foreground focus:outline-none"
                    />
                    <span className="text-[10px] text-muted-foreground">%</span>
                  </div>
                </div>
                <p className="text-[10px] text-muted-foreground">
                  {confidenceThreshold === null
                    ? "Off — drag the slider or enter a % to filter"
                    : confidenceDirection === "above"
                      ? `Showing locations with confidence ≥ ${confidenceThreshold}%`
                      : `Showing locations with confidence ≤ ${confidenceThreshold}% (needs updating)`}
                </p>
              </div>

              {/* Specificity threshold */}
              <div className="flex flex-col gap-1.5 border-t border-border pt-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Address specificity
                  </span>
                  {specificityThreshold !== null && (
                    <button
                      onClick={() => setSpecificityThreshold(null)}
                      className="text-[10px] text-muted-foreground hover:text-foreground"
                    >
                      Off
                    </button>
                  )}
                </div>
                <DirectionToggle
                  value={specificityDirection}
                  options={[
                    { value: "at_least", label: "At least" },
                    { value: "at_most", label: "At most" },
                  ]}
                  onChange={setSpecificityDirection}
                />
                <select
                  value={specificityThreshold ?? ""}
                  onChange={(e) =>
                    setSpecificityThreshold(
                      e.target.value === ""
                        ? null
                        : (e.target.value as LocationSpecificity)
                    )
                  }
                  className="w-full rounded border border-border bg-background px-1.5 py-1 text-xs text-foreground focus:outline-none"
                >
                  <option value="">Off</option>
                  {LOCATION_SPECIFICITY_LEVELS.map((level) => (
                    <option key={level} value={level}>
                      {LOCATION_SPECIFICITY_LABELS[level]}
                    </option>
                  ))}
                </select>
                <p className="text-[10px] text-muted-foreground">
                  {specificityThreshold === null
                    ? "Off — unknown < continent < country < region < city < district < street < exact address"
                    : specificityDirection === "at_least"
                      ? `Showing locations at least as specific as ${LOCATION_SPECIFICITY_LABELS[specificityThreshold]}`
                      : `Showing locations no more specific than ${LOCATION_SPECIFICITY_LABELS[specificityThreshold]}`}
                </p>
              </div>
            </div>
          </PopoverContent>
        </Popover>

        {/* Needs review toggle */}
        <Button
          variant={needsReviewMode ? "secondary" : "ghost"}
          size="sm"
          className="h-7 text-xs"
          onClick={toggleNeedsReviewMode}
        >
          <ListChecks className="mr-1 size-3.5" />
          Needs review
          {reviewCount > 0 && (
            <Badge
              variant={needsReviewMode ? "amber" : "outline"}
              className="ml-1 text-[9px]"
            >
              {reviewCount}
            </Badge>
          )}
        </Button>

        {/* Proximity toggle */}
        <Button
          variant={proximityMode || proximityAnchorKey ? "secondary" : "ghost"}
          size="sm"
          className="h-7 text-xs"
          onClick={toggleProximityMode}
        >
          <Crosshair className="mr-1 size-3.5" />
          Proximity
          {proximityAnchorKey ? (
            <Badge variant="amber" className="ml-1 text-[9px]">
              Active
            </Badge>
          ) : proximityMode ? (
            <Badge variant="secondary" className="ml-1 text-[9px]">
              Selecting...
            </Badge>
          ) : null}
        </Button>

        {/* Bounding area drawing */}
        <Popover
          open={areasOpen}
          onOpenChange={(open) => {
            // While drawing, map clicks land "outside" the popover and Radix
            // would dismiss it — keep it open so Finish/Apply stay reachable
            if (!open && drawMode) return
            setAreasOpen(open)
          }}
        >
          <PopoverTrigger asChild>
            <Button
              variant={
                drawMode || shapeFilterActive || draftShapeActive
                  ? "secondary"
                  : "ghost"
              }
              size="sm"
              className="h-7 text-xs"
            >
              <Pencil className="mr-1 size-3.5" />
              Areas
              {shapeFilterActive ? (
                <Badge variant="amber" className="ml-1 text-[9px]">
                  {boundingShapes.length}
                </Badge>
              ) : draftShapeActive ? (
                <Badge variant="secondary" className="ml-1 text-[9px]">
                  {draftBoundingShapes.length}
                </Badge>
              ) : drawMode ? (
                <Badge variant="secondary" className="ml-1 text-[9px]">
                  Drawing
                </Badge>
              ) : null}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-64 p-2">
            <div className="mb-2 flex items-center justify-between gap-2 px-1">
              <span className="text-xs font-medium">Area filter</span>
              <span className="text-[10px] text-muted-foreground">
                {visibleCount} of {locations.length}
              </span>
            </div>

            <div className="mb-2 grid grid-cols-2 gap-1">
              <Button
                variant={drawTool === "box" ? "secondary" : "ghost"}
                size="sm"
                className="h-7 text-xs"
                onClick={() => setDrawTool("box")}
              >
                <BoxSelect className="size-3.5" />
                Box
              </Button>
              <Button
                variant={drawTool === "polygon" ? "secondary" : "ghost"}
                size="sm"
                className="h-7 text-xs"
                onClick={() => setDrawTool("polygon")}
              >
                <Waypoints className="size-3.5" />
                Polygon
              </Button>
            </div>

            <Button
              variant={drawMode ? "secondary" : "outline"}
              size="sm"
              className="mb-2 h-7 w-full text-xs"
              onClick={toggleDrawMode}
            >
              <Pencil className="size-3.5" />
              {drawMode ? "Stop drawing" : "Draw area"}
            </Button>

            {drawMode && drawTool === "polygon" && (
              <div className="mb-2 grid grid-cols-[1fr_auto_auto_auto] items-center gap-1 border-b border-border pb-2">
                <span className="px-1 text-[10px] text-muted-foreground">
                  {drawingPoints.length} point
                  {drawingPoints.length !== 1 ? "s" : ""}
                </span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Undo last point"
                  disabled={drawingPoints.length === 0}
                  onClick={undoLastDrawingPoint}
                >
                  <Undo2 className="size-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Cancel drawing"
                  disabled={drawingPoints.length === 0}
                  onClick={cancelDrawingShape}
                >
                  <X className="size-3.5" />
                </Button>
                <Button
                  variant="outline"
                  size="icon-sm"
                  aria-label="Finish area"
                  disabled={drawingPoints.length < 3}
                  onClick={finishDrawingShape}
                >
                  <Check className="size-3.5" />
                </Button>
              </div>
            )}

            {drawMode && drawTool === "box" && drawingPoints.length > 0 && (
              <div className="mb-2 grid grid-cols-[1fr_auto] items-center gap-1 border-b border-border pb-2">
                <span className="px-1 text-[10px] text-muted-foreground">
                  Box draft
                </span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Cancel drawing"
                  onClick={cancelDrawingShape}
                >
                  <X className="size-3.5" />
                </Button>
              </div>
            )}

            {draftBoundingShapes.length > 0 && (
              <div className="mb-2 space-y-1 border-b border-border pb-2">
                <div className="flex items-center justify-between px-1">
                  <span className="text-[10px] font-medium text-muted-foreground">
                    Pending
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {draftBoundingShapes.length}
                  </span>
                </div>
                {draftBoundingShapes.map((shape, index) => (
                  <div
                    key={shape.id}
                    className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
                  >
                    <span>Area {index + 1}</span>
                    <span className="ml-auto text-[10px] text-muted-foreground">
                      {Math.max(shape.coordinates.length - 1, 0)} points
                    </span>
                    <button
                      type="button"
                      className="rounded p-0.5 text-muted-foreground hover:bg-background hover:text-foreground"
                      aria-label={`Remove pending area ${index + 1}`}
                      onClick={() => removeDraftBoundingShape(shape.id)}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                ))}
                <div className="grid grid-cols-2 gap-1 pt-1">
                  <Button
                    variant="secondary"
                    size="sm"
                    className="h-7 text-xs"
                    disabled={drawingPoints.length > 0}
                    onClick={applyBoundingShapeFilter}
                  >
                    <Check className="size-3.5" />
                    Apply
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={discardBoundingShapeDraft}
                  >
                    <X className="size-3.5" />
                    Discard
                  </Button>
                </div>
              </div>
            )}

            {boundingShapes.length > 0 ? (
              <div className="space-y-1">
                <div className="flex items-center justify-between px-1">
                  <span className="text-[10px] font-medium text-muted-foreground">
                    Applied
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {boundingShapes.length}
                  </span>
                </div>
                {boundingShapes.map((shape, index) => (
                  <div
                    key={shape.id}
                    className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
                  >
                    <span>Area {index + 1}</span>
                    <span className="ml-auto text-[10px] text-muted-foreground">
                      {Math.max(shape.coordinates.length - 1, 0)} points
                    </span>
                    <button
                      type="button"
                      className="rounded p-0.5 text-muted-foreground hover:bg-background hover:text-foreground"
                      aria-label={`Remove area ${index + 1}`}
                      onClick={() => removeBoundingShape(shape.id)}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={clearBoundingShapes}
                  className="mt-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <Trash2 className="size-3.5" />
                  Clear areas
                </button>
              </div>
            ) : draftBoundingShapes.length === 0 ? (
              <div className="rounded-md border border-dashed border-border px-2 py-2 text-center text-[10px] text-muted-foreground">
                No areas
              </div>
            ) : null}
          </PopoverContent>
        </Popover>

        <div className="flex-1" />

        {/* Count */}
        <span className="text-[10px] text-muted-foreground">
          {locations.length} location{locations.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Active filter banner: the map is NOT showing the full picture */}
      {(needsReviewMode || confidenceFilterActive || shapeFilterActive) && (
        <div className="flex items-center gap-2 border-b border-amber-500/40 bg-yellow-500/15 px-3 py-1 text-[11px] font-medium text-yellow-700 dark:text-yellow-400">
          {shapeFilterActive ? (
            <Pencil className="size-3.5" />
          ) : (
            <ShieldCheck className="size-3.5" />
          )}
          {`Showing ${visibleCount} of ${locations.length} locations (${activeFilterLabels.join(", ")})`}
          {needsReviewMode && reviewCount > 0
            ? `; ${reviewCount} total locations need review`
            : ""}
          <button
            onClick={clearActiveFilters}
            className="ml-auto flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-yellow-500/20"
          >
            <X className="size-3" />
            Clear
          </button>
        </div>
      )}
    </>
  )
}
