import { useState } from "react"
import { ChevronDown, ChevronRight } from "lucide-react"
import { NodeBadge } from "@/components/ui/node-badge"
import { Badge } from "@/components/ui/badge"

import { cn } from "@/lib/cn"
import type { ConnectionGroup } from "@/types/graph.types"

interface ConnectionsListProps {
  connections: ConnectionGroup[]
  onNodeClick?: (key: string) => void
  className?: string
}

export function ConnectionsList({
  connections,
  onNodeClick,
  className,
}: ConnectionsListProps) {
  const relType = (g: ConnectionGroup) => g.relationshipType ?? "unknown"

  const [expanded, setExpanded] = useState<Set<string>>(
    new Set(connections.map((c) => relType(c)))
  )

  const toggleGroup = (type: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  if (connections.length === 0) {
    return (
      <p className="py-3 text-center text-xs text-muted-foreground">
        No connections
      </p>
    )
  }

  return (
    <div className={cn(className)}>
      <div className="space-y-1">
        {connections.map((group) => {
          const type = relType(group)
          return (
          <div key={type}>
            <button
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-muted/50"
              onClick={() => toggleGroup(type)}
            >
              {expanded.has(type) ? (
                <ChevronDown className="size-3 text-muted-foreground" />
              ) : (
                <ChevronRight className="size-3 text-muted-foreground" />
              )}
              <span className="flex-1 text-xs font-medium text-foreground uppercase tracking-wider truncate">
                {type.replace(/_/g, " ")}
              </span>
              <Badge variant="slate" className="text-[10px]">
                {(group.nodes ?? []).length}
              </Badge>
            </button>

            {expanded.has(type) && (
              <div className="ml-5 space-y-0.5">
                {(group.nodes ?? []).map((node) => (
                  <button
                    key={node.key}
                    className="flex w-full items-center gap-2 rounded px-2 py-1 text-left hover:bg-muted/50"
                    onClick={() => onNodeClick?.(node.key)}
                  >
                    <NodeBadge type={node.type} />
                    <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                      {node.label}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
          )
        })}
      </div>
    </div>
  )
}
