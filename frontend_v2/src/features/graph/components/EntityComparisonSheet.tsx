import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { NodeBadge } from "@/components/ui/node-badge"
import { ConfidenceBar } from "@/components/ui/confidence-bar"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { NodeDetail } from "@/types/graph.types"

interface EntityComparisonSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  entity1: NodeDetail | null
  entity2: NodeDetail | null
}

export function EntityComparisonSheet({ open, onOpenChange, entity1, entity2 }: EntityComparisonSheetProps) {
  if (!entity1 || !entity2) return null

  const allKeys = new Set([
    ...Object.keys(entity1.properties),
    ...Object.keys(entity2.properties),
  ])
  const hiddenKeys = new Set(["key", "label", "type", "x", "y", "case_id", "node_key"])
  const propKeys = [...allKeys].filter((k) => !hiddenKeys.has(k))

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[600px] overflow-auto sm:max-w-[600px]">
        <SheetHeader>
          <SheetTitle>Compare Entities</SheetTitle>
        </SheetHeader>

        <div className="mt-4 grid grid-cols-2 gap-4">
          {/* Entity headers */}
          {[entity1, entity2].map((entity) => (
            <div key={entity.key} className="rounded-lg border p-3">
              <NodeBadge type={entity.type} />
              <p className="mt-1 text-sm font-semibold">{entity.label}</p>
              {entity.confidence !== undefined && (
                <ConfidenceBar value={entity.confidence} className="mt-2" />
              )}
              <p className="mt-1 text-[10px] text-muted-foreground">
                {entity.connections.reduce((sum, g) => sum + g.nodes.length, 0)} connections
              </p>
            </div>
          ))}
        </div>

        <Separator className="my-4" />

        <h4 className="mb-2 text-xs font-medium text-muted-foreground">Properties</h4>
        <ScrollArea className="max-h-[400px]">
          <div className="space-y-0.5">
            {propKeys.map((key) => {
              const v1 = entity1.properties[key]
              const v2 = entity2.properties[key]
              const differ = String(v1 ?? "") !== String(v2 ?? "")
              return (
                <div key={key} className="grid grid-cols-[100px_1fr_1fr] gap-2 rounded px-2 py-1.5 hover:bg-muted/50">
                  <span className="text-xs font-medium text-muted-foreground">{key.replace(/_/g, " ")}</span>
                  <span className={`text-xs ${differ ? "text-amber-400" : "text-foreground"}`}>
                    {v1 !== undefined && v1 !== null ? String(v1) : "\u2014"}
                  </span>
                  <span className={`text-xs ${differ ? "text-amber-400" : "text-foreground"}`}>
                    {v2 !== undefined && v2 !== null ? String(v2) : "\u2014"}
                  </span>
                </div>
              )
            })}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
