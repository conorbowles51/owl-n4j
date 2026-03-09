import type { MapLocation } from "./MapCanvas"

interface HeatmapLayerProps {
  locations: MapLocation[]
  visible: boolean
  radius?: number
  intensity?: number
}

export function HeatmapLayer({ locations, visible }: HeatmapLayerProps) {
  if (!visible || locations.length === 0) return null

  // Placeholder — will integrate with Leaflet.heat plugin
  return (
    <div className="absolute bottom-12 right-3 rounded-lg border border-border bg-card/90 px-3 py-2 backdrop-blur">
      <p className="text-[10px] font-semibold text-muted-foreground">
        Heatmap active — {locations.length} points
      </p>
    </div>
  )
}
