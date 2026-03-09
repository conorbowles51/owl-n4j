import { useState } from "react"
import { ChevronDown, ChevronRight } from "lucide-react"
import { NodeBadge } from "@/components/ui/node-badge"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
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
  const [expanded, setExpanded] = useState<Set<string>>(
    new Set(connections.map((c) => c.relationshipType))
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
    <ScrollArea className={cn("max-h-[400px]", className)}>
      <div className="space-y-1">
        {connections.map((group) => (
          <div key={group.relationshipType}>
            <button
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-muted/50"
              onClick={() => toggleGroup(group.relationshipType)}
            >
              {expanded.has(group.relationshipType) ? (
                <ChevronDown className="size-3 text-muted-foreground" />
              ) : (
                <ChevronRight className="size-3 text-muted-foreground" />
              )}
              <span className="flex-1 text-xs font-medium text-foreground uppercase tracking-wider">
                {group.relationshipType.replace(/_/g, " ")}
              </span>
              <Badge variant="slate" className="text-[10px]">
                {group.nodes.length}
              </Badge>
            </button>

            {expanded.has(group.relationshipType) && (
              <div className="ml-5 space-y-0.5">
                {group.nodes.map((node) => (
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
        ))}
      </div>
    </ScrollArea>
  )
}
