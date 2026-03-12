import { NodeBadge } from "@/components/ui/node-badge"
import type { EntityType } from "@/lib/theme"

interface Trail {
  entityKey: string
  entityName: string
  entityType: EntityType
  points: { latitude: number; longitude: number; timestamp: string }[]
}

interface MovementTrailsProps {
  trails: Trail[]
  visible: boolean
}

/** Placeholder — movement trail rendering deferred to later phase */
export function MovementTrails({ trails, visible }: MovementTrailsProps) {
  if (!visible || trails.length === 0) return null

  return (
    <div className="absolute bottom-12 left-3 max-h-32 w-48 overflow-auto rounded-lg border border-border bg-card/90 p-2 backdrop-blur">
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Trails
      </p>
      {trails.map((trail) => (
        <div key={trail.entityKey} className="flex items-center gap-1.5 py-0.5">
          <NodeBadge type={trail.entityType} />
          <span className="truncate text-[10px]">{trail.entityName}</span>
          <span className="text-[9px] text-muted-foreground">
            {trail.points.length} pts
          </span>
        </div>
      ))}
    </div>
  )
}
