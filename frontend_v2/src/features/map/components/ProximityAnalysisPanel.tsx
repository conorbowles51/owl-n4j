import { Crosshair } from "lucide-react"
import { Slider } from "@/components/ui/slider"
import { Badge } from "@/components/ui/badge"
import { NodeBadge } from "@/components/ui/node-badge"
import { EmptyState } from "@/components/ui/empty-state"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { MapLocation } from "./MapCanvas"

interface ProximityResult {
  location: MapLocation
  distance: number
}

interface ProximityAnalysisPanelProps {
  anchor?: MapLocation
  radius: number
  onRadiusChange: (radius: number) => void
  results: ProximityResult[]
}

export function ProximityAnalysisPanel({
  anchor,
  radius,
  onRadiusChange,
  results,
}: ProximityAnalysisPanelProps) {
  if (!anchor) {
    return (
      <EmptyState
        icon={Crosshair}
        title="No anchor point"
        description="Select a location to analyze nearby entities"
        className="py-8"
      />
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Crosshair className="size-3.5 text-amber-500" />
        <span className="text-xs font-semibold">Proximity to</span>
        <NodeBadge type={anchor.type} />
        <span className="truncate text-xs">{anchor.label}</span>
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

      <ScrollArea className="max-h-48">
        <div className="space-y-1">
          {results.length === 0 ? (
            <p className="py-4 text-center text-xs text-muted-foreground">
              No locations within {radius} km
            </p>
          ) : (
            results.map((r) => (
              <div
                key={r.location.key}
                className="flex items-center gap-2 rounded-md px-2 py-1 text-xs hover:bg-muted"
              >
                <NodeBadge type={r.location.type} />
                <span className="flex-1 truncate">{r.location.label}</span>
                <span className="font-mono text-[10px] text-muted-foreground">
                  {r.distance.toFixed(1)} km
                </span>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
