import { useMemo } from "react"
import { NodeBadge } from "@/components/ui/node-badge"
import { cn } from "@/lib/cn"
import { nodeColors, type EntityType } from "@/lib/theme"
import type { TimelineEvent } from "../api"

interface TimelineCanvasProps {
  events: TimelineEvent[]
  selectedEventId?: string
  onSelectEvent?: (event: TimelineEvent) => void
  zoom: number
}

interface SwimLane {
  entityKey: string
  entityName: string
  entityType: EntityType
  events: TimelineEvent[]
}

export function TimelineCanvas({
  events,
  selectedEventId,
  onSelectEvent,
  zoom,
}: TimelineCanvasProps) {
  const swimLanes = useMemo(() => {
    const laneMap = new Map<string, SwimLane>()

    for (const event of events) {
      const key = event.entity_key || "__unknown__"
      if (!laneMap.has(key)) {
        laneMap.set(key, {
          entityKey: key,
          entityName: event.entity_name || "Unknown",
          entityType: (event.entity_type || "Unknown") as EntityType,
          events: [],
        })
      }
      laneMap.get(key)!.events.push(event)
    }

    // Sort events within each lane
    for (const lane of laneMap.values()) {
      lane.events.sort(
        (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
      )
    }

    return Array.from(laneMap.values())
  }, [events])

  const markerSize = Math.max(8, Math.min(16, zoom * 10))

  return (
    <div className="space-y-4 p-4">
      {swimLanes.map((lane) => (
        <div key={lane.entityKey} className="rounded-lg border border-border">
          {/* Lane header */}
          <div className="flex items-center gap-2 border-b border-border bg-muted/30 px-3 py-1.5">
            <NodeBadge type={lane.entityType} />
            <span className="text-xs font-medium">{lane.entityName}</span>
            <span className="text-[10px] text-muted-foreground">
              {lane.events.length} events
            </span>
          </div>

          {/* Lane events */}
          <div className="relative overflow-x-auto px-3 py-2">
            <div className="relative border-l-2 border-border pl-6">
              {lane.events.map((event) => {
                const color =
                  nodeColors[lane.entityType] || "#64748B"
                return (
                  <div
                    key={event.id}
                    className={cn(
                      "relative mb-3 cursor-pointer last:mb-0",
                      selectedEventId === event.id &&
                        "rounded-md bg-amber-500/10"
                    )}
                    onClick={() => onSelectEvent?.(event)}
                  >
                    <div
                      className="absolute -left-[25px] top-1 rounded-full border-2 border-background"
                      style={{
                        width: markerSize,
                        height: markerSize,
                        backgroundColor: color,
                      }}
                    />
                    <div className="rounded-md px-2 py-1.5 hover:bg-muted/50">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[10px] text-muted-foreground">
                          {new Date(event.date).toLocaleDateString()}
                        </span>
                        <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium">
                          {event.type}
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs">{event.description}</p>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
