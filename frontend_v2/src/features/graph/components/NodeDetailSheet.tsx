import { useGraphStore } from "@/stores/graph.store"
import { useNodeDetails } from "../hooks/use-node-details"
import { NodeBadge } from "@/components/ui/node-badge"
import { ConfidenceBar } from "@/components/ui/confidence-bar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { X, Pencil, Expand, Eye } from "lucide-react"
import type { EntityType } from "@/lib/theme"

interface NodeDetailSheetProps {
  caseId: string
}

export function NodeDetailSheet({ caseId }: NodeDetailSheetProps) {
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)
  const clearSelection = useGraphStore((s) => s.clearSelection)

  const firstKey = Array.from(selectedNodeKeys)[0] ?? null
  const { data: detail, isLoading } = useNodeDetails(firstKey, caseId)

  if (selectedNodeKeys.size > 1) {
    return (
      <div className="flex h-full flex-col border-l border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-4 py-2">
          <span className="text-sm font-semibold">
            {selectedNodeKeys.size} nodes selected
          </span>
          <Button variant="ghost" size="icon-sm" onClick={clearSelection}>
            <X className="size-3.5" />
          </Button>
        </div>
        <div className="p-4 text-xs text-muted-foreground">
          Multi-selection actions: merge, compare, create subgraph
        </div>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center border-l border-border bg-card">
        <LoadingSpinner />
      </div>
    )
  }

  if (!detail) return null

  return (
    <div className="flex h-full flex-col border-l border-border bg-card">
      {/* Header */}
      <div className="flex items-start justify-between border-b border-border px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1.5">
            <NodeBadge type={detail.type as EntityType} />
          </div>
          <h3 className="truncate text-sm font-semibold">{detail.label}</h3>
          {detail.confidence !== undefined && (
            <div className="mt-1.5 max-w-[200px]">
              <ConfidenceBar value={detail.confidence} />
            </div>
          )}
        </div>
        <div className="flex gap-1">
          <Button variant="ghost" size="icon-sm">
            <Pencil className="size-3.5" />
          </Button>
          <Button variant="ghost" size="icon-sm">
            <Expand className="size-3.5" />
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={clearSelection}>
            <X className="size-3.5" />
          </Button>
        </div>
      </div>

      <ScrollArea className="flex-1">
        {/* Properties */}
        <div className="px-4 py-3">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Properties
          </h4>
          <div className="space-y-1.5">
            {Object.entries(detail.properties).map(([key, value]) => (
              <div key={key} className="flex gap-2 text-xs">
                <span className="shrink-0 text-muted-foreground">{key}:</span>
                <span className="truncate font-medium">{String(value)}</span>
              </div>
            ))}
          </div>
        </div>

        <Separator />

        {/* Connections */}
        <div className="px-4 py-3">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Connections
          </h4>
          {detail.connections.length === 0 ? (
            <p className="text-xs text-muted-foreground">No connections</p>
          ) : (
            <div className="space-y-3">
              {detail.connections.map((group) => (
                <div key={group.relationshipType}>
                  <Badge variant="outline" className="mb-1.5">
                    {group.relationshipType}
                  </Badge>
                  <div className="space-y-1">
                    {group.nodes.map((n) => (
                      <div
                        key={n.key}
                        className="flex items-center gap-2 text-xs"
                      >
                        <NodeBadge type={n.type as EntityType}>
                          {n.label}
                        </NodeBadge>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <Separator />

        {/* Sources */}
        <div className="px-4 py-3">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Sources
          </h4>
          {detail.sources.length === 0 ? (
            <p className="text-xs text-muted-foreground">No sources</p>
          ) : (
            <div className="space-y-1.5">
              {detail.sources.map((src) => (
                <div
                  key={src.fileId}
                  className="flex items-center gap-2 text-xs"
                >
                  <Eye className="size-3 text-muted-foreground" />
                  <span className="truncate">{src.fileName}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
