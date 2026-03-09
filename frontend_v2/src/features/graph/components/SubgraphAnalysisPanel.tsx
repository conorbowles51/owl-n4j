import { Badge } from "@/components/ui/badge"
import { NodeBadge } from "@/components/ui/node-badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Network, Hash, GitBranch } from "lucide-react"
import type { GraphData } from "@/types/graph.types"

interface SubgraphAnalysisPanelProps {
  data: GraphData
  className?: string
}

export function SubgraphAnalysisPanel({ data, className }: SubgraphAnalysisPanelProps) {
  const typeDistribution = data.nodes.reduce<Record<string, number>>((acc, n) => {
    acc[n.type] = (acc[n.type] ?? 0) + 1
    return acc
  }, {})

  const relTypeDistribution = data.edges.reduce<Record<string, number>>((acc, e) => {
    acc[e.type] = (acc[e.type] ?? 0) + 1
    return acc
  }, {})

  const avgConnections = data.nodes.length > 0
    ? (data.edges.length * 2 / data.nodes.length).toFixed(1)
    : "0"

  return (
    <div className={className}>
      <h3 className="mb-3 text-sm font-semibold">Subgraph Analysis</h3>

      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-md bg-muted p-2 text-center">
          <Network className="mx-auto mb-1 size-4 text-amber-500" />
          <p className="text-lg font-semibold">{data.nodes.length}</p>
          <p className="text-[10px] text-muted-foreground">Nodes</p>
        </div>
        <div className="rounded-md bg-muted p-2 text-center">
          <GitBranch className="mx-auto mb-1 size-4 text-amber-500" />
          <p className="text-lg font-semibold">{data.edges.length}</p>
          <p className="text-[10px] text-muted-foreground">Edges</p>
        </div>
        <div className="rounded-md bg-muted p-2 text-center">
          <Hash className="mx-auto mb-1 size-4 text-amber-500" />
          <p className="text-lg font-semibold">{avgConnections}</p>
          <p className="text-[10px] text-muted-foreground">Avg Connections</p>
        </div>
      </div>

      <Separator className="my-3" />

      <h4 className="mb-1.5 text-xs font-medium text-muted-foreground">Entity Types</h4>
      <div className="space-y-1">
        {Object.entries(typeDistribution).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
          <div key={type} className="flex items-center justify-between rounded px-2 py-1 hover:bg-muted/50">
            <NodeBadge type={type} />
            <Badge variant="slate" className="text-[10px]">{count}</Badge>
          </div>
        ))}
      </div>

      <Separator className="my-3" />

      <h4 className="mb-1.5 text-xs font-medium text-muted-foreground">Relationship Types</h4>
      <ScrollArea className="max-h-[150px]">
        <div className="space-y-1">
          {Object.entries(relTypeDistribution).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
            <div key={type} className="flex items-center justify-between rounded px-2 py-1 hover:bg-muted/50">
              <span className="text-xs text-foreground">{type.replace(/_/g, " ")}</span>
              <Badge variant="slate" className="text-[10px]">{count}</Badge>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
