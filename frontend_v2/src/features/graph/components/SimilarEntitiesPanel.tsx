import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { NodeBadge } from "@/components/ui/node-badge"
import { ConfidenceBar } from "@/components/ui/confidence-bar"
import { ScrollArea } from "@/components/ui/scroll-area"
import { EmptyState } from "@/components/ui/empty-state"
import { GitMerge, X, Users } from "lucide-react"
import type { EntityType } from "@/lib/theme"

interface SimilarPair {
  key1: string
  label1: string
  type1: EntityType
  key2: string
  label2: string
  type2: EntityType
  similarity: number
}

interface SimilarEntitiesPanelProps {
  pairs: SimilarPair[]
  onMerge?: (key1: string, key2: string) => void
  onDismiss?: (key1: string, key2: string) => void
  className?: string
}

export function SimilarEntitiesPanel({
  pairs,
  onMerge,
  onDismiss,
  className,
}: SimilarEntitiesPanelProps) {
  if (pairs.length === 0) {
    return (
      <EmptyState
        icon={Users}
        title="No similar entities found"
        description="Run similarity analysis to find potential duplicates"
        className={className}
      />
    )
  }

  return (
    <div className={className}>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold">Similar Entities</h3>
        <Badge variant="amber">{pairs.length} pairs</Badge>
      </div>
      <ScrollArea className="max-h-[400px]">
        <div className="space-y-2">
          {pairs.map((pair) => (
            <div
              key={`${pair.key1}-${pair.key2}`}
              className="rounded-lg border p-3"
            >
              <div className="mb-2 flex items-center justify-between">
                <ConfidenceBar value={pair.similarity} className="flex-1" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="flex items-center gap-1.5">
                  <NodeBadge type={pair.type1} />
                  <span className="min-w-0 truncate text-xs">{pair.label1}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <NodeBadge type={pair.type2} />
                  <span className="min-w-0 truncate text-xs">{pair.label2}</span>
                </div>
              </div>
              <div className="mt-2 flex gap-2">
                {onMerge && (
                  <Button variant="outline" size="sm" onClick={() => onMerge(pair.key1, pair.key2)}>
                    <GitMerge className="size-3" />
                    Merge
                  </Button>
                )}
                {onDismiss && (
                  <Button variant="ghost" size="sm" onClick={() => onDismiss(pair.key1, pair.key2)}>
                    <X className="size-3" />
                    Dismiss
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
