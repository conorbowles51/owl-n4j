import { useMemo } from "react"
import { locationsToGeoJSON } from "../lib/geojson"
import type { MapLocation } from "./use-map-data"

export function useHeatmapData(locations: MapLocation[]) {
  return useMemo(() => locationsToGeoJSON(locations), [locations])
}
