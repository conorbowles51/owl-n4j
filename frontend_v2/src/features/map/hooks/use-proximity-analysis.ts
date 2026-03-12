import { useMemo } from "react"
import { haversineDistance, type MapLocation } from "./use-map-data"
import { useMapStore } from "../stores/map.store"

export interface ProximityResult {
  location: MapLocation
  distance: number
}

export function useProximityAnalysis(locations: MapLocation[]) {
  const anchorKey = useMapStore((s) => s.proximityAnchorKey)
  const radius = useMapStore((s) => s.proximityRadius)

  const anchor = useMemo(
    () => locations.find((l) => l.key === anchorKey) ?? null,
    [locations, anchorKey]
  )

  const results = useMemo<ProximityResult[]>(() => {
    if (!anchor) return []
    return locations
      .filter((l) => l.key !== anchor.key)
      .map((l) => ({
        location: l,
        distance: haversineDistance(
          anchor.latitude,
          anchor.longitude,
          l.latitude,
          l.longitude
        ),
      }))
      .filter((r) => r.distance <= radius)
      .sort((a, b) => a.distance - b.distance)
  }, [locations, anchor, radius])

  return { anchor, results, radius }
}
