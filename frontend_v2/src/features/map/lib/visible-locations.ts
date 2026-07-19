import {
  matchesLocationFilters,
  needsReview,
  type LocationFilterState,
} from "@/lib/location-confidence"
import type { BoundingShape } from "../stores/map.store"
import type { MapLocation } from "../hooks/use-map-data"
import { pointInAnyShape } from "./geometry"

interface LocationFilters extends LocationFilterState {
  hiddenTypes: Set<string>
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
    if (!filters.needsReviewMode && !matchesLocationFilters(location, filters)) {
      return false
    }
    return pointInAnyShape(
      [location.longitude, location.latitude],
      filters.boundingShapes
    )
  })
}
