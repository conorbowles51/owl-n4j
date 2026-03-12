import { ChevronRight, Home, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { NodeBadge } from "@/components/ui/node-badge"
import { Badge } from "@/components/ui/badge"
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area"
import type { RelationshipNavEntry } from "../stores/table.store"

interface RelationshipBreadcrumbProps {
  navigationStack: RelationshipNavEntry[]
  onPopToIndex: (index: number) => void
}

export function RelationshipBreadcrumb({
  navigationStack,
  onPopToIndex,
}: RelationshipBreadcrumbProps) {
  if (navigationStack.length === 0) return null

  return (
    <div className="flex items-center border-b border-border bg-muted/30 h-9">
      <ScrollArea className="min-w-0 flex-1 overflow-hidden">
        <div className="flex items-center gap-1 whitespace-nowrap px-4 h-9">
          {/* Root crumb */}
          <button
            onClick={() => onPopToIndex(-1)}
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors shrink-0"
          >
            <Home className="size-3" />
            All Entities
          </button>

          {/* Nav entries */}
          {navigationStack.map((entry, idx) => {
            const isLast = idx === navigationStack.length - 1

            return (
              <span key={`${entry.nodeKey}-${idx}`} className="inline-flex items-center gap-1 shrink-0">
                <ChevronRight className="size-3 text-muted-foreground/50" />

                {/* Relationship type badges (from parent to this node) */}
                {entry.relationshipTypes.length > 0 && (
                  <span className="inline-flex items-center gap-0.5">
                    {entry.relationshipTypes.map((relType) => (
                      <Badge
                        key={relType}
                        variant="outline"
                        className="text-[10px] px-1 py-0 h-4 font-mono text-amber-600 dark:text-amber-400 border-amber-500/30"
                      >
                        {relType}
                      </Badge>
                    ))}
                    <ChevronRight className="size-3 text-muted-foreground/50" />
                  </span>
                )}

                {/* Node badge + label */}
                {isLast ? (
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-foreground">
                    <NodeBadge type={entry.nodeType} />
                    {entry.nodeLabel}
                  </span>
                ) : (
                  <button
                    onClick={() => onPopToIndex(idx)}
                    className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
                  >
                    <NodeBadge type={entry.nodeType} />
                    {entry.nodeLabel}
                  </button>
                )}
              </span>
            )
          })}
        </div>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>

      {/* Back to all button — pinned outside scroll area */}
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 mr-2 text-xs text-muted-foreground shrink-0"
        onClick={() => onPopToIndex(-1)}
      >
        <X className="size-3" />
        Back to all
      </Button>
    </div>
  )
}
