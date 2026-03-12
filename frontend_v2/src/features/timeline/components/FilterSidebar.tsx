import { X } from "lucide-react"
import { Checkbox } from "@/components/ui/checkbox"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { NodeBadge } from "@/components/ui/node-badge"
import { getEventTypeColor } from "../api"
import type { DerivedEntity } from "../lib/timeline-utils"

interface FilterSidebarProps {
  eventTypes: string[]
  selectedTypes: Set<string>
  onToggleType: (type: string) => void
  onSelectAllTypes: () => void
  onClearAllTypes: () => void
  entities: DerivedEntity[]
  selectedEntityKeys: Set<string>
  entityFilterCounts: Map<string, number>
  onToggleEntity: (key: string) => void
  onClearEntityFilter: () => void
  onFocusEntity: (key: string) => void
  activeFilterCount: number
  onClearAll: () => void
}

export function FilterSidebar({
  eventTypes,
  selectedTypes,
  onToggleType,
  onSelectAllTypes,
  onClearAllTypes,
  entities,
  selectedEntityKeys,
  entityFilterCounts,
  onToggleEntity,
  onClearEntityFilter,
  onFocusEntity,
  activeFilterCount,
  onClearAll,
}: FilterSidebarProps) {
  // Group entities by type
  const entityGroups = entities.reduce(
    (acc, entity) => {
      const group = acc.get(entity.type) ?? []
      group.push(entity)
      acc.set(entity.type, group)
      return acc
    },
    new Map<string, DerivedEntity[]>()
  )

  return (
    <div className="flex h-full flex-col">
      <ScrollArea className="flex-1">
        {/* Event Types */}
        <div className="px-3 py-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Event Types
            </span>
            <div className="flex gap-1">
              <button
                onClick={onSelectAllTypes}
                className="text-[10px] text-muted-foreground hover:text-foreground"
              >
                All
              </button>
              <span className="text-[10px] text-muted-foreground">|</span>
              <button
                onClick={onClearAllTypes}
                className="text-[10px] text-muted-foreground hover:text-foreground"
              >
                None
              </button>
            </div>
          </div>
          <div className="space-y-0.5">
            {eventTypes.map((type) => (
              <button
                key={type}
                onClick={() => onToggleType(type)}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-xs hover:bg-muted"
              >
                <Checkbox checked={selectedTypes.has(type)} />
                <span
                  className="size-2 rounded-full shrink-0"
                  style={{ backgroundColor: getEventTypeColor(type) }}
                />
                <span className="flex-1 text-left">{type}</span>
              </button>
            ))}
          </div>
        </div>

        <Separator />

        {/* Entities */}
        <div className="px-3 py-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Entities
            </span>
            {selectedEntityKeys.size > 0 && (
              <button
                onClick={onClearEntityFilter}
                className="text-[10px] text-muted-foreground hover:text-foreground"
              >
                Clear
              </button>
            )}
          </div>
          {Array.from(entityGroups.entries()).map(([type, groupEntities]) => (
            <div key={type} className="mb-2">
              <p className="text-[10px] font-medium text-muted-foreground mb-0.5 px-1 capitalize">
                {type}
              </p>
              <div className="space-y-0.5">
                {groupEntities.map((entity) => {
                  const count = entityFilterCounts.get(entity.key) ?? 0
                  return (
                    <div
                      key={entity.key}
                      className="flex items-center gap-1.5 rounded-md px-1 py-0.5 hover:bg-muted"
                    >
                      <button
                        onClick={() => onToggleEntity(entity.key)}
                        className="flex items-center gap-1.5 flex-1 min-w-0"
                      >
                        <Checkbox
                          checked={selectedEntityKeys.has(entity.key)}
                        />
                        <NodeBadge type={entity.type} className="text-[9px] py-0 shrink-0">
                          {entity.name}
                        </NodeBadge>
                        <span className="text-[10px] text-muted-foreground shrink-0">
                          {count}
                        </span>
                      </button>
                      <button
                        onClick={() => onFocusEntity(entity.key)}
                        className="text-[9px] text-muted-foreground hover:text-foreground shrink-0"
                        title="Focus on this entity only"
                      >
                        Focus
                      </button>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>

      {/* Active filter chips */}
      {activeFilterCount > 0 && (
        <div className="border-t border-border p-2">
          <Button
            variant="ghost"
            size="sm"
            className="w-full text-xs"
            onClick={onClearAll}
          >
            <X className="size-3 mr-1" />
            Clear all filters ({activeFilterCount})
          </Button>
        </div>
      )}
    </div>
  )
}
