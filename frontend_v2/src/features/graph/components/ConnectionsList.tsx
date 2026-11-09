import { useState } from "react"
import { ChevronDown, ChevronRight } from "lucide-react"
import { NodeBadge } from "@/components/ui/node-badge"
import { Badge } from "@/components/ui/badge"

import { cn } from "@/lib/cn"
import type { ConnectionGroup } from "@/types/graph.types"
import { SignificantRelationshipButton } from "@/features/significant/components/SignificantRelationshipButton"
import { entityPanelColour } from "../lib/entity-panel-colours"

interface ConnectionsListProps {
  connections: ConnectionGroup[]
  onNodeClick?: (key: string) => void
  className?: string
  /** With both, each relationship gets a star to mark it significant (GR-01). */
  caseId?: string
  entity?: { key: string; label: string }
}

export function ConnectionsList({
  connections,
  onNodeClick,
  className,
  caseId,
  entity,
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
                {(group.nodes ?? []).map((node) => {
                  const outgoing = node.direction !== "incoming"
                  const words = type.replace(/_/g, " ").toLowerCase()
                  return (
                  <div key={`${node.key}-${node.direction ?? ""}`} className="flex items-center gap-1">
                    <button
                      className="flex min-w-0 flex-1 items-center gap-2 rounded px-2 py-1 text-left hover:bg-muted/50"
                      onClick={() => onNodeClick?.(node.key)}
                    >
                      <NodeBadge type={node.type} color={entityPanelColour(node.type)} />
                      <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                        {node.label}
                      </span>
                    </button>
                    {caseId && entity && node.direction && (
                      <SignificantRelationshipButton
                        caseId={caseId}
                        compact
                        surface="entity_panel"
                        relationship={{
                          source_key: outgoing ? entity.key : node.key,
                          type,
                          target_key: outgoing ? node.key : entity.key,
                        }}
                        description={outgoing ? `${entity.label} ${words} ${node.label}` : `${node.label} ${words} ${entity.label}`}
                      />
                    )}
                  </div>
                  )
                })}
              </div>
            )}
          </div>
          )
        })}
      </div>
    </div>
  )
}
