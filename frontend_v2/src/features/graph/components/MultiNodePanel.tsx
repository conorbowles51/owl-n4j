import { GitMerge, EyeOff, Network, BarChart3 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { NodeBadge } from "@/components/ui/node-badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/cn"
import type { GraphNode } from "@/types/graph.types"

interface MultiNodePanelProps {
  nodes: GraphNode[]
  onMerge?: () => void
  onHideSelected?: () => void
  onCreateSubgraph?: () => void
  onCompare?: () => void
  onClearSelection?: () => void
  className?: string
}

export function MultiNodePanel({
  nodes,
  onMerge,
  onHideSelected,
  onCreateSubgraph,
  onCompare,
  onClearSelection,
  className,
}: MultiNodePanelProps) {
  // Group by entity type
  const typeGroups = nodes.reduce<Record<string, number>>((acc, node) => {
    acc[node.type] = (acc[node.type] ?? 0) + 1
    return acc
  }, {})

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground">
            {nodes.length} nodes selected
          </h3>
          <div className="mt-1 flex flex-wrap gap-1">
            {Object.entries(typeGroups).map(([type, count]) => (
              <div key={type} className="flex items-center gap-1">
                <NodeBadge type={type} />
                <span className="text-[10px] text-muted-foreground">&times;{count}</span>
              </div>
            ))}
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={onClearSelection}>
          Clear
        </Button>
      </div>

      <Separator />

      {/* Bulk actions */}
      <div className="grid grid-cols-2 gap-2">
        {onMerge && nodes.length >= 2 && (
          <Button variant="outline" size="sm" onClick={onMerge}>
            <GitMerge className="size-3.5" />
            Merge
          </Button>
        )}
        {onCompare && nodes.length === 2 && (
          <Button variant="outline" size="sm" onClick={onCompare}>
            <BarChart3 className="size-3.5" />
            Compare
          </Button>
        )}
        {onHideSelected && (
          <Button variant="outline" size="sm" onClick={onHideSelected}>
            <EyeOff className="size-3.5" />
            Hide All
          </Button>
        )}
        {onCreateSubgraph && (
          <Button variant="outline" size="sm" onClick={onCreateSubgraph}>
            <Network className="size-3.5" />
            Subgraph
          </Button>
        )}
      </div>

      <Separator />

      {/* Selected nodes list */}
      <div>
        <h4 className="mb-1.5 text-xs font-medium text-muted-foreground">
          Selected Entities
        </h4>
        <ScrollArea className="max-h-[300px]">
          <div className="space-y-0.5">
            {nodes.map((node) => (
              <div
                key={node.key}
                className="flex items-center gap-2 rounded px-2 py-1 hover:bg-muted/50"
              >
                <NodeBadge type={node.type} />
                <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                  {node.label}
                </span>
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}
