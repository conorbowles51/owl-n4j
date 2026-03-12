import { Route, ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { NodeBadge } from "@/components/ui/node-badge"
import { EmptyState } from "@/components/ui/empty-state"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { MapLocation } from "../hooks/use-map-data"

interface RouteSegment {
  from: MapLocation
  to: MapLocation
  distance: number
  duration?: string
}

interface RouteAnalysisPanelProps {
  route: RouteSegment[]
  onClear: () => void
}

export function RouteAnalysisPanel({ route, onClear }: RouteAnalysisPanelProps) {
  if (route.length === 0) {
    return (
      <EmptyState
        icon={Route}
        title="No route selected"
        description="Select two or more locations to analyze the route"
        className="py-8"
      />
    )
  }

  const totalDistance = route.reduce((sum, s) => sum + s.distance, 0)

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Route className="size-3.5 text-amber-500" />
          <span className="text-xs font-semibold">Route Analysis</span>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="slate">{totalDistance.toFixed(1)} km</Badge>
          <Button variant="ghost" size="sm" onClick={onClear}>
            Clear
          </Button>
        </div>
      </div>

      <ScrollArea className="max-h-48">
        <div className="space-y-1">
          {route.map((segment, i) => (
            <div
              key={`${segment.from.key}-${segment.to.key}`}
              className="flex items-center gap-2 rounded-md border border-border px-2 py-1.5 text-xs"
            >
              <span className="text-[10px] text-muted-foreground">{i + 1}</span>
              <NodeBadge type={segment.from.type} />
              <span className="truncate">{segment.from.name}</span>
              <ArrowRight className="size-3 text-muted-foreground" />
              <NodeBadge type={segment.to.type} />
              <span className="truncate">{segment.to.name}</span>
              <Badge variant="outline" className="ml-auto">
                {segment.distance.toFixed(1)} km
              </Badge>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
