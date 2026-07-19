import {
  Crosshair,
  Layers,
  ListChecks,
  RefreshCw,
  ShieldCheck,
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
import { fetchAPI } from "@/lib/api-client"
import { useQueryClient } from "@tanstack/react-query"
import { useMapReviewQueue, type MapLocation } from "../hooks/use-map-data"
import {
  LOCATION_SPECIFICITY_LEVELS,
  LOCATION_SPECIFICITY_LABELS,
  matchesLocationFilters,
  needsReview,
  type LocationSpecificity,
} from "@/lib/location-confidence"

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
  const queryClient = useQueryClient()
  const showHeatmap = useMapStore((s) => s.showHeatmap)
  const toggleHeatmap = useMapStore((s) => s.toggleHeatmap)
  const proximityMode = useMapStore((s) => s.proximityMode)
  const proximityAnchorKey = useMapStore((s) => s.proximityAnchorKey)
  const toggleProximityMode = useMapStore((s) => s.toggleProximityMode)
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
  const visibleMapLocations = locations.filter((loc) => {
    if (hiddenTypes.has(loc.type)) return false
    if (needsReviewMode) return needsReview(loc)
    return matchesLocationFilters(loc, filters)
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

  const handleRescan = async () => {
    await fetchAPI(`/api/graph/cases/${caseId}/rescan-locations`, {
      method: "POST",
    })
    queryClient.invalidateQueries({ queryKey: ["map", caseId] })
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

        <div className="flex-1" />

        {/* Rescan button */}
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          onClick={handleRescan}
        >
          <RefreshCw className="mr-1 size-3.5" />
          Rescan
        </Button>

        {/* Count */}
        <span className="text-[10px] text-muted-foreground">
          {locations.length} location{locations.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Active filter banner: the map is NOT showing the full picture */}
      {(needsReviewMode || confidenceFilterActive) && (
        <div className="flex items-center gap-2 border-b border-amber-500/40 bg-yellow-500/15 px-3 py-1 text-[11px] font-medium text-yellow-700 dark:text-yellow-400">
          <ShieldCheck className="size-3.5" />
          {needsReviewMode
            ? `Needs review mode: showing ${visibleCount} of ${locations.length} map pins; ${reviewCount} total locations need review`
            : `Filter active (${filterSummary}): showing ${visibleCount} of ${locations.length} locations`}
          <button
            onClick={clearLocationFilters}
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
