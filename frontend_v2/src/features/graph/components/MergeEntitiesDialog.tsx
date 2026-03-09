import { useState } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NodeBadge } from "@/components/ui/node-badge"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import type { GraphNode } from "@/types/graph.types"
import { graphAPI } from "../api"

interface MergeEntitiesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  entity1: GraphNode | null
  entity2: GraphNode | null
  caseId: string
  similarity?: number
  onMerged?: () => void
}

export function MergeEntitiesDialog({
  open,
  onOpenChange,
  entity1,
  entity2,
  caseId,
  similarity,
  onMerged,
}: MergeEntitiesDialogProps) {
  const [mergedName, setMergedName] = useState("")
  const [keepEntity, setKeepEntity] = useState<1 | 2>(1)
  const [saving, setSaving] = useState(false)

  const handleMerge = async () => {
    if (!entity1 || !entity2) return
    setSaving(true)
    try {
      const source = keepEntity === 1 ? entity2.key : entity1.key
      const target = keepEntity === 1 ? entity1.key : entity2.key
      await graphAPI.mergeEntities(caseId, source, target, mergedName ? { name: mergedName } : undefined)
      onMerged?.()
      onOpenChange(false)
    } finally {
      setSaving(false)
    }
  }

  if (!entity1 || !entity2) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Merge Entities</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          {similarity !== undefined && (
            <Badge variant="amber">Similarity: {Math.round(similarity * 100)}%</Badge>
          )}
          <div className="grid grid-cols-2 gap-3">
            <button
              className={`rounded-lg border p-3 text-left transition-colors ${keepEntity === 1 ? "border-amber-500 bg-amber-500/5" : "border-border hover:border-muted-foreground"}`}
              onClick={() => setKeepEntity(1)}
            >
              <div className="mb-1 flex items-center gap-1.5">
                <NodeBadge type={entity1.type} />
                {keepEntity === 1 && <Badge variant="amber" className="text-[10px]">Keep</Badge>}
              </div>
              <p className="text-sm font-medium">{entity1.label}</p>
              <p className="mt-1 text-[10px] text-muted-foreground">{entity1.key}</p>
            </button>
            <button
              className={`rounded-lg border p-3 text-left transition-colors ${keepEntity === 2 ? "border-amber-500 bg-amber-500/5" : "border-border hover:border-muted-foreground"}`}
              onClick={() => setKeepEntity(2)}
            >
              <div className="mb-1 flex items-center gap-1.5">
                <NodeBadge type={entity2.type} />
                {keepEntity === 2 && <Badge variant="amber" className="text-[10px]">Keep</Badge>}
              </div>
              <p className="text-sm font-medium">{entity2.label}</p>
              <p className="mt-1 text-[10px] text-muted-foreground">{entity2.key}</p>
            </button>
          </div>
          <Separator />
          <div>
            <label className="mb-1 block text-xs font-medium">Merged Name (optional)</label>
            <Input
              value={mergedName}
              onChange={(e) => setMergedName(e.target.value)}
              placeholder={keepEntity === 1 ? entity1.label : entity2.label}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" onClick={handleMerge} disabled={saving}>
            {saving ? "Merging..." : "Merge"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
