import { ZoomIn, ZoomOut, Maximize2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Slider } from "@/components/ui/slider"
import { Badge } from "@/components/ui/badge"

interface TimelineControlsProps {
  startDate: string
  endDate: string
  onStartDateChange: (date: string) => void
  onEndDateChange: (date: string) => void
  zoom: number
  onZoomChange: (zoom: number) => void
  eventCount: number
}

export function TimelineControls({
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
  zoom,
  onZoomChange,
  eventCount,
}: TimelineControlsProps) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-1.5">
        <label className="text-[10px] text-muted-foreground">From</label>
        <Input
          type="date"
          value={startDate}
          onChange={(e) => onStartDateChange(e.target.value)}
          className="h-7 w-32 text-xs"
        />
      </div>
      <div className="flex items-center gap-1.5">
        <label className="text-[10px] text-muted-foreground">To</label>
        <Input
          type="date"
          value={endDate}
          onChange={(e) => onEndDateChange(e.target.value)}
          className="h-7 w-32 text-xs"
        />
      </div>

      <div className="mx-2 h-4 w-px bg-border" />

      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => onZoomChange(Math.max(0.5, zoom - 0.25))}
        >
          <ZoomOut className="size-3.5" />
        </Button>
        <Slider
          value={[zoom]}
          onValueChange={([v]) => onZoomChange(v)}
          min={0.5}
          max={3}
          step={0.25}
          className="w-20"
        />
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => onZoomChange(Math.min(3, zoom + 0.25))}
        >
          <ZoomIn className="size-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => onZoomChange(1)}
          title="Reset zoom"
        >
          <Maximize2 className="size-3.5" />
        </Button>
      </div>

      <div className="flex-1" />

      <Badge variant="slate">{eventCount} events</Badge>
    </div>
  )
}
