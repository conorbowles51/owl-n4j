import { Flame } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { NodeBadge } from "@/components/ui/node-badge"
import { EmptyState } from "@/components/ui/empty-state"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Slider } from "@/components/ui/slider"
import type { MapLocation } from "../hooks/use-map-data"
import type { EntityType } from "@/lib/theme"

export interface Hotspot {
  center: MapLocation
  count: number
  radius: number
  locations: MapLocation[]
}

interface HotspotPanelProps {
  hotspots: Hotspot[]
  sensitivity: number
  onSensitivityChange: (value: number) => void
  onSelectHotspot?: (hotspot: Hotspot) => void
}

export function HotspotPanel({
  hotspots,
  sensitivity,
  onSensitivityChange,
  onSelectHotspot,
}: HotspotPanelProps) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Flame className="size-3.5 text-amber-500" />
        <span className="text-xs font-semibold">Hotspot Detection</span>
        {hotspots.length > 0 && (
          <Badge variant="amber">{hotspots.length}</Badge>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span className="text-[10px] text-muted-foreground">Sensitivity</span>
        <Slider
          value={[sensitivity]}
          onValueChange={([v]) => onSensitivityChange(v)}
          min={1}
          max={10}
          step={1}
          className="flex-1"
        />
        <span className="w-6 text-center text-[10px] text-muted-foreground">
          {sensitivity}
        </span>
      </div>

      {hotspots.length === 0 ? (
        <EmptyState
          icon={Flame}
          title="No hotspots detected"
          description="Adjust sensitivity or add more location data"
          className="py-8"
        />
      ) : (
        <ScrollArea className="max-h-64">
          <div className="space-y-1">
            {hotspots.map((hotspot, i) => (
              <button
                key={hotspot.center.key}
                onClick={() => onSelectHotspot?.(hotspot)}
                className="flex w-full items-center gap-2 rounded-md border border-border px-2 py-1.5 text-xs hover:bg-muted"
              >
                <span className="font-mono text-[10px] text-muted-foreground">
                  #{i + 1}
                </span>
                <NodeBadge type={hotspot.center.type as EntityType} />
                <span className="flex-1 truncate text-left">
                  {hotspot.center.name}
                </span>
                <Badge variant="outline">{hotspot.count} pts</Badge>
              </button>
            ))}
          </div>
        </ScrollArea>
      )}
    </div>
  )
}
