import { Layers, ZoomIn, ZoomOut, Maximize2, Thermometer, Route } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Checkbox } from "@/components/ui/checkbox"

interface MapControlsProps {
  showHeatmap: boolean
  onToggleHeatmap: () => void
  showClusters: boolean
  onToggleClusters: () => void
  showTrails: boolean
  onToggleTrails: () => void
  onZoomIn: () => void
  onZoomOut: () => void
  onFitBounds: () => void
}

export function MapControls({
  showHeatmap,
  onToggleHeatmap,
  showClusters,
  onToggleClusters,
  showTrails,
  onToggleTrails,
  onZoomIn,
  onZoomOut,
  onFitBounds,
}: MapControlsProps) {
  return (
    <div className="flex items-center gap-1">
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="ghost" size="sm">
            <Layers className="size-3.5" />
            Layers
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-48 p-1">
          <button
            onClick={onToggleHeatmap}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
          >
            <Checkbox checked={showHeatmap} />
            <Thermometer className="size-3" />
            Heatmap
          </button>
          <button
            onClick={onToggleClusters}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
          >
            <Checkbox checked={showClusters} />
            <Layers className="size-3" />
            Clusters
          </button>
          <button
            onClick={onToggleTrails}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted"
          >
            <Checkbox checked={showTrails} />
            <Route className="size-3" />
            Movement trails
          </button>
        </PopoverContent>
      </Popover>

      <div className="mx-1 h-4 w-px bg-border" />

      <Button variant="ghost" size="icon-sm" onClick={onZoomIn}>
        <ZoomIn className="size-3.5" />
      </Button>
      <Button variant="ghost" size="icon-sm" onClick={onZoomOut}>
        <ZoomOut className="size-3.5" />
      </Button>
      <Button variant="ghost" size="icon-sm" onClick={onFitBounds} title="Fit all">
        <Maximize2 className="size-3.5" />
      </Button>
    </div>
  )
}
