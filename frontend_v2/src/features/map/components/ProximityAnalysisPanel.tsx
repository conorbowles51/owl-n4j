import { Crosshair } from "lucide-react"
import { Slider } from "@/components/ui/slider"
import { Badge } from "@/components/ui/badge"
import { NodeBadge } from "@/components/ui/node-badge"
import { EmptyState } from "@/components/ui/empty-state"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { MapLocation } from "../hooks/use-map-data"
import type { EntityType } from "@/lib/theme"

export interface ProximityResult {
  location: MapLocation
  distance: number
}

interface ProximityAnalysisPanelProps {
  anchor: MapLocation | null
  radius: number
  onRadiusChange: (radius: number) => void
  results: ProximityResult[]
  onSelectResult?: (location: MapLocation) => void
}

export function ProximityAnalysisPanel({
  anchor,
  radius,
  onRadiusChange,
  results,
  onSelectResult,
}: ProximityAnalysisPanelProps) {
  if (!anchor) {
    return (
      <EmptyState
        icon={Crosshair}
        title="No anchor point"
        description="Select a location and click 'Set as anchor' to analyze nearby entities"
        className="py-8"
      />
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Crosshair className="size-3.5 text-amber-500" />
        <span className="text-xs font-semibold">Proximity to</span>
        <NodeBadge type={anchor.type as EntityType} />
        <span className="truncate text-xs">{anchor.name}</span>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-[10px] text-muted-foreground">Radius</span>
        <Slider
          value={[radius]}
          onValueChange={([v]) => onRadiusChange(v)}
          min={0.1}
          max={50}
          step={0.5}
          className="flex-1"
        />
        <Badge variant="outline">{radius} km</Badge>
      </div>

      <ScrollArea className="max-h-64">
        <div className="space-y-1">
          {results.length === 0 ? (
            <p className="py-4 text-center text-xs text-muted-foreground">
              No locations within {radius} km
            </p>
          ) : (
            <>
              <p className="text-[10px] text-muted-foreground">
                {results.length} location{results.length !== 1 ? "s" : ""} found
              </p>
              {results.map((r) => (
                <button
                  key={r.location.key}
                  onClick={() => onSelectResult?.(r.location)}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-xs hover:bg-muted"
                >
                  <NodeBadge type={r.location.type as EntityType} />
                  <span className="flex-1 truncate text-left">
                    {r.location.name}
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {r.distance.toFixed(1)} km
                  </span>
                </button>
              ))}
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
