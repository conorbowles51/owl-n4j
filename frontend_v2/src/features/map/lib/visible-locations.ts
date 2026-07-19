import { getConfidenceTier, needsReview } from "@/lib/location-confidence"
import type { BoundingShape } from "../stores/map.store"
import type { MapLocation } from "../hooks/use-map-data"
import { pointInAnyShape } from "./geometry"

interface LocationFilters {
  hiddenTypes: Set<string>
  hiddenConfidenceTiers: Set<string>
  needsReviewMode: boolean
  boundingShapes: BoundingShape[]
}

export function getVisibleLocations(
  locations: MapLocation[],
  filters: LocationFilters
) {
  return locations.filter((location) => {
    if (filters.hiddenTypes.has(location.type)) return false
    if (filters.needsReviewMode && !needsReview(location)) return false
    if (
      !filters.needsReviewMode &&
      filters.hiddenConfidenceTiers.has(getConfidenceTier(location))
    ) {
      return false
    }
    return pointInAnyShape(
      [location.longitude, location.latitude],
      filters.boundingShapes
    )
  })
}
