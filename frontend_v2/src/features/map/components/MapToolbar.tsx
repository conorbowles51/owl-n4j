import { Crosshair, Layers, ListChecks, RefreshCw, ShieldCheck, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Checkbox } from "@/components/ui/checkbox"
import { useMapStore } from "../stores/map.store"
import { fetchAPI } from "@/lib/api-client"
import { useQueryClient } from "@tanstack/react-query"
import { useMapReviewQueue, type MapLocation } from "../hooks/use-map-data"
import {
  CONFIDENCE_TIERS,
  CONFIDENCE_TIER_LABELS,
  getConfidenceTier,
  needsReview,
} from "@/lib/location-confidence"

interface MapToolbarProps {
  caseId: string
  locations: MapLocation[]
}

export function MapToolbar({ caseId, locations }: MapToolbarProps) {
  const queryClient = useQueryClient()
  const showHeatmap = useMapStore((s) => s.showHeatmap)
  const toggleHeatmap = useMapStore((s) => s.toggleHeatmap)
  const proximityMode = useMapStore((s) => s.proximityMode)
  const proximityAnchorKey = useMapStore((s) => s.proximityAnchorKey)
  const toggleProximityMode = useMapStore((s) => s.toggleProximityMode)
  const hiddenConfidenceTiers = useMapStore((s) => s.hiddenConfidenceTiers)
  const hiddenTypes = useMapStore((s) => s.hiddenTypes)
  const toggleConfidenceTier = useMapStore((s) => s.toggleConfidenceTier)
  const clearConfidenceFilter = useMapStore((s) => s.clearConfidenceFilter)
  const needsReviewMode = useMapStore((s) => s.needsReviewMode)
  const toggleNeedsReviewMode = useMapStore((s) => s.toggleNeedsReviewMode)

  const { data: flaggedQueue } = useMapReviewQueue(caseId)

  // Review queue = low-confidence pins + flagged geocodes with no pin
  const reviewPinCount = locations.filter(needsReview).length
  const flaggedReviewCount = (flaggedQueue ?? []).filter(needsReview).length
  const reviewCount = reviewPinCount + flaggedReviewCount

  const tierCounts = new Map<string, number>()
  for (const loc of locations) {
    const tier = getConfidenceTier(loc)
    tierCounts.set(tier, (tierCounts.get(tier) ?? 0) + 1)
  }

  const confidenceFilterActive = hiddenConfidenceTiers.size > 0
  const visibleMapLocations = locations.filter((loc) => {
    if (hiddenTypes.has(loc.type)) return false
    if (needsReviewMode) return needsReview(loc)
    return !hiddenConfidenceTiers.has(getConfidenceTier(loc))
  })
  const visibleCount = visibleMapLocations.length

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
            <Checkbox checked={showHeatmap} />
            Heatmap
          </button>
        </PopoverContent>
      </Popover>

      {/* Confidence filter */}
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
                Filtered
              </Badge>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-48 p-1">
          {CONFIDENCE_TIERS.map((tier) => (
            <button
              key={tier}
              onClick={() => toggleConfidenceTier(tier)}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
            >
              <Checkbox checked={!hiddenConfidenceTiers.has(tier)} />
              {CONFIDENCE_TIER_LABELS[tier]}
              <span className="ml-auto text-[10px] text-muted-foreground">
                {tierCounts.get(tier) ?? 0}
              </span>
            </button>
          ))}
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
          : `Confidence filter active: showing ${visibleCount} of ${locations.length} locations`}
        <button
          onClick={clearConfidenceFilter}
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
