import { useState, useMemo } from "react"
import { Search, Eye, EyeOff } from "lucide-react"
import { Input } from "@/components/ui/input"
import { NodeBadge } from "@/components/ui/node-badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/cn"
import type { EntityType } from "@/lib/theme"

interface EntityDockEntry {
  key: string
  name: string
  type: EntityType
  eventCount: number
}

interface EntityDockProps {
  entities: EntityDockEntry[]
  hiddenKeys: Set<string>
  onToggle: (key: string) => void
  onShowAll: () => void
  onHideAll: () => void
}

export function EntityDock({
  entities,
  hiddenKeys,
  onToggle,
  onShowAll,
  onHideAll,
}: EntityDockProps) {
  const [search, setSearch] = useState("")

  const filtered = useMemo(
    () =>
      entities.filter(
        (e) =>
          e.name.toLowerCase().includes(search.toLowerCase()) ||
          e.type.toLowerCase().includes(search.toLowerCase())
      ),
    [entities, search]
  )

  const visibleCount = entities.length - hiddenKeys.size

  return (
    <div className="flex w-56 flex-col border-r border-border">
      <div className="border-b border-border px-3 py-2">
        <div className="flex items-center justify-between">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Entities ({visibleCount}/{entities.length})
          </p>
          <div className="flex gap-1">
            <button
              onClick={onShowAll}
              className="text-[10px] text-muted-foreground hover:text-foreground"
            >
              All
            </button>
            <span className="text-[10px] text-muted-foreground">|</span>
            <button
              onClick={onHideAll}
              className="text-[10px] text-muted-foreground hover:text-foreground"
            >
              None
            </button>
          </div>
        </div>
        <div className="relative mt-1.5">
          <Search className="absolute left-2 top-1.5 size-3 text-muted-foreground" />
          <Input
            placeholder="Filter..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-6 pl-7 text-[10px]"
          />
        </div>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-1">
          {filtered.map((entity) => {
            const hidden = hiddenKeys.has(entity.key)
            return (
              <button
                key={entity.key}
                onClick={() => onToggle(entity.key)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-2 py-1 text-xs hover:bg-muted",
                  hidden && "opacity-40"
                )}
              >
                {hidden ? (
                  <EyeOff className="size-3 text-muted-foreground" />
                ) : (
                  <Eye className="size-3 text-muted-foreground" />
                )}
                <NodeBadge type={entity.type} />
                <span className="flex-1 truncate text-left">{entity.name}</span>
                <span className="text-[10px] text-muted-foreground">
                  {entity.eventCount}
                </span>
              </button>
            )
          })}
        </div>
      </ScrollArea>
    </div>
  )
}
