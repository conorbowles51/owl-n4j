import { Crosshair, Layers } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Checkbox } from "@/components/ui/checkbox"
import { useMapStore } from "../stores/map.store"
import type { MapLocation } from "../hooks/use-map-data"

interface MapToolbarProps {
  locations: MapLocation[]
}

export function MapToolbar({ locations }: MapToolbarProps) {
  const showHeatmap = useMapStore((s) => s.showHeatmap)
  const toggleHeatmap = useMapStore((s) => s.toggleHeatmap)
  const proximityMode = useMapStore((s) => s.proximityMode)
  const proximityAnchorKey = useMapStore((s) => s.proximityAnchorKey)
  const toggleProximityMode = useMapStore((s) => s.toggleProximityMode)

  return (
    <div className="flex items-center gap-1.5 border-b border-border bg-card px-3 py-1.5">
      {/* Layer toggles */}
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="ghost" size="sm" className="h-7 text-xs">
            <Layers className="mr-1 size-3.5" />
            Layers
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-44 p-1">
          <button
            onClick={toggleHeatmap}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
          >
            <Checkbox checked={showHeatmap} />
            Heatmap
          </button>
        </PopoverContent>
      </Popover>

      {/* Proximity toggle */}
      <Button
        variant={proximityMode || proximityAnchorKey ? "secondary" : "ghost"}
        size="sm"
        className="h-7 text-xs"
        onClick={toggleProximityMode}
      >
        <Crosshair className="mr-1 size-3.5" />
        Proximity
        {proximityAnchorKey ? (
          <Badge variant="amber" className="ml-1 text-[9px]">
            Active
          </Badge>
        ) : proximityMode ? (
          <Badge variant="secondary" className="ml-1 text-[9px]">
            Selecting…
          </Badge>
        ) : null}
      </Button>

      <div className="flex-1" />

      {/* Count */}
      <span className="text-[10px] text-muted-foreground">
        {locations.length} location{locations.length !== 1 ? "s" : ""}
      </span>
    </div>
  )
}
