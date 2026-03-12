import { ZoomIn, ZoomOut, Maximize2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

interface MapControlsProps {
  onZoomIn: () => void
  onZoomOut: () => void
  onFitBounds: () => void
}

export function MapControls({
  onZoomIn,
  onZoomOut,
  onFitBounds,
}: MapControlsProps) {
  return (
    <div className="absolute right-3 top-3 z-10 flex flex-col gap-1 rounded-lg border border-border bg-card/95 p-1 shadow-md backdrop-blur">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon-sm" onClick={onZoomIn}>
            <ZoomIn className="size-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="left">Zoom in</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon-sm" onClick={onZoomOut}>
            <ZoomOut className="size-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="left">Zoom out</TooltipContent>
      </Tooltip>
      <div className="mx-1 h-px bg-border" />
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon-sm" onClick={onFitBounds}>
            <Maximize2 className="size-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="left">Fit all</TooltipContent>
      </Tooltip>
    </div>
  )
}
