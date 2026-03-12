import { Source, Layer } from "react-map-gl/maplibre"
import { heatmapLayer } from "../lib/map-styles"
import { locationsToGeoJSON } from "../lib/geojson"
import type { MapLocation } from "../hooks/use-map-data"
import { useMemo } from "react"

interface HeatmapLayerProps {
  locations: MapLocation[]
  visible: boolean
}

export function HeatmapLayer({ locations, visible }: HeatmapLayerProps) {
  const geojson = useMemo(() => locationsToGeoJSON(locations), [locations])

  if (!visible || locations.length === 0) return null

  return (
    <Source id="heatmap-source" type="geojson" data={geojson}>
      <Layer {...heatmapLayer} />
    </Source>
  )
}
