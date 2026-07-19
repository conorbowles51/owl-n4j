import { MapPinOff } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { useGraphStore } from "@/stores/graph.store"
import { useMapStore } from "../stores/map.store"
import { useMapReviewQueue, type MapLocation } from "../hooks/use-map-data"
import {
  CONFIDENCE_TIER_BADGE_VARIANTS,
  CONFIDENCE_TIER_LABELS,
  LOCATION_SPECIFICITY_LABELS,
  confidencePercent,
  getConfidenceTier,
  getLocationSpecificity,
  needsReview,
  reviewReason,
} from "@/lib/location-confidence"

interface NeedsReviewPanelProps {
  caseId: string
  locations: MapLocation[]
}

/**
 * Review queue for the needs-review mode: low-confidence pins plus locations
 * flagged at ingestion (which have no pin). Selecting an item
 * opens the shared detail panel, from which the relocate flow is reachable.
 */
export function NeedsReviewPanel({ caseId, locations }: NeedsReviewPanelProps) {
  const { data: flaggedQueue } = useMapReviewQueue(caseId)
  const selectNodes = useGraphStore((s) => s.selectNodes)
  const flyTo = useMapStore((s) => s.flyTo)

  const reviewPins = locations.filter(needsReview)
  const flagged = (flaggedQueue ?? []).filter(needsReview)
  const total = reviewPins.length + flagged.length

  return (
    <div className="absolute right-3 top-14 z-10 flex max-h-[60%] w-72 flex-col rounded-lg border border-border bg-card/95 shadow-md backdrop-blur">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Needs review
        </span>
        <Badge variant="amber" className="ml-auto text-[9px]">
          {total}
        </Badge>
      </div>

      <div className="flex-1 overflow-y-auto p-1.5">
        {total === 0 && (
          <p className="px-2 py-3 text-center text-[11px] text-muted-foreground">
            No locations need review
          </p>
        )}

        {reviewPins.map((loc) => (
          <button
            key={loc.key}
            onClick={() => {
              selectNodes([loc.key])
              flyTo({ longitude: loc.longitude, latitude: loc.latitude })
            }}
            className="flex w-full flex-col gap-0.5 rounded-md px-2 py-1.5 text-left hover:bg-muted"
          >
            <span className="flex items-center gap-1.5">
              <span className="truncate text-xs font-medium">{loc.name}</span>
              <Badge
                variant={CONFIDENCE_TIER_BADGE_VARIANTS[getConfidenceTier(loc)]}
                className="ml-auto shrink-0 text-[9px]"
              >
                {CONFIDENCE_TIER_LABELS[getConfidenceTier(loc)]}
              </Badge>
            </span>
            <span className="truncate text-[10px] text-muted-foreground">
              {reviewReason(loc)}
              {loc.location_raw ? ` - "${loc.location_raw}"` : ""}
            </span>
            <span className="truncate text-[10px] text-muted-foreground">
              {confidencePercent(loc)}% confidence ·{" "}
              {LOCATION_SPECIFICITY_LABELS[getLocationSpecificity(loc)]}
            </span>
          </button>
        ))}

        {flagged.map((item) => (
          <button
            key={item.key}
            onClick={() => selectNodes([item.key])}
            className="flex w-full flex-col gap-0.5 rounded-md px-2 py-1.5 text-left hover:bg-muted"
          >
            <span className="flex items-center gap-1.5">
              <MapPinOff className="size-3 shrink-0 text-muted-foreground" />
              <span className="truncate text-xs font-medium">{item.name}</span>
              <Badge
                variant={CONFIDENCE_TIER_BADGE_VARIANTS[getConfidenceTier(item)]}
                className="ml-auto shrink-0 text-[9px]"
              >
                {CONFIDENCE_TIER_LABELS[getConfidenceTier(item)]}
              </Badge>
            </span>
            <span className="truncate text-[10px] text-muted-foreground">
              {reviewReason(item)}
              {item.location_raw ? ` - "${item.location_raw}"` : ""} - no pin
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
