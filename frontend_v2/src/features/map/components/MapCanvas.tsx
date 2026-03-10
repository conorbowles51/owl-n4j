import { useRef } from "react"
import { MapPin } from "lucide-react"
import { nodeColors, type EntityType } from "@/lib/theme"

export interface MapLocation {
  key: string
  label: string
  type: EntityType
  latitude: number
  longitude: number
}

interface MapCanvasProps {
  locations: MapLocation[]
  selectedKey?: string
  onSelectLocation?: (location: MapLocation) => void
  showHeatmap?: boolean
  showClusters?: boolean
}

export function MapCanvas({
  locations,
  selectedKey,
  onSelectLocation,
}: MapCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  // Leaflet integration point — will initialize map here when leaflet is added
  // For now, render a visual placeholder with location markers

  return (
    <div ref={containerRef} className="relative h-full w-full bg-slate-100 dark:bg-slate-900">
      {/* Map background placeholder */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-center">
          <MapPin className="mx-auto mb-2 size-12 text-amber-500/30" />
          <p className="text-sm text-muted-foreground">
            Map canvas — Leaflet integration pending
          </p>
          <p className="text-xs text-muted-foreground">
            {locations.length} locations ready to render
          </p>
        </div>
      </div>

      {/* Floating location markers (positioned in a grid as placeholder) */}
      <div className="absolute inset-0 overflow-hidden p-8">
        <div className="grid h-full grid-cols-6 gap-2">
          {locations.slice(0, 24).map((loc) => {
            const color = nodeColors[loc.type] || "#64748B"
            const isSelected = selectedKey === loc.key
            return (
              <button
                key={loc.key}
                onClick={() => onSelectLocation?.(loc)}
                className="group flex flex-col items-center justify-center gap-1 rounded-lg border border-transparent p-1 transition hover:border-border hover:bg-muted/30"
                style={isSelected ? { borderColor: color } : undefined}
              >
                <div
                  className="size-3 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="max-w-full truncate text-[9px] text-muted-foreground group-hover:text-foreground">
                  {loc.label}
                </span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
