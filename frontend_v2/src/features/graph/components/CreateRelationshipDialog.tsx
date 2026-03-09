import { useState } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { NodeBadge } from "@/components/ui/node-badge"
import { ArrowRight } from "lucide-react"
import type { GraphNode } from "@/types/graph.types"
import { graphAPI } from "../api"

interface CreateRelationshipDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  sourceNodes: GraphNode[]
  targetNodes: GraphNode[]
  caseId: string
  onCreated?: () => void
}

export function CreateRelationshipDialog({
  open,
  onOpenChange,
  sourceNodes,
  targetNodes,
  caseId,
  onCreated,
}: CreateRelationshipDialogProps) {
  const [relType, setRelType] = useState("")
  const [notes, setNotes] = useState("")
  const [saving, setSaving] = useState(false)

  const handleCreate = async () => {
    if (!relType.trim()) return
    setSaving(true)
    try {
      const relationships = sourceNodes.flatMap((src) =>
        targetNodes.map((tgt) => ({
          source: src.key,
          target: tgt.key,
          type: relType.toUpperCase().replace(/\s+/g, "_"),
        }))
      )
      await graphAPI.createRelationships(relationships, caseId)
      onCreated?.()
      onOpenChange(false)
      setRelType("")
      setNotes("")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Create Relationship</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex items-center gap-2 rounded-md bg-muted p-3">
            <div className="min-w-0 flex-1">
              <p className="text-xs text-muted-foreground">From</p>
              {sourceNodes.map((n) => (
                <div key={n.key} className="flex items-center gap-1.5 py-0.5">
                  <NodeBadge type={n.type} />
                  <span className="truncate text-xs">{n.label}</span>
                </div>
              ))}
            </div>
            <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <p className="text-xs text-muted-foreground">To</p>
              {targetNodes.map((n) => (
                <div key={n.key} className="flex items-center gap-1.5 py-0.5">
                  <NodeBadge type={n.type} />
                  <span className="truncate text-xs">{n.label}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Relationship Type</label>
            <Input value={relType} onChange={(e) => setRelType(e.target.value)} placeholder="e.g. WORKS_FOR, LOCATED_AT" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Notes (optional)</label>
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Additional context..." />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" onClick={handleCreate} disabled={!relType.trim() || saving}>
            {saving ? "Creating..." : `Create ${sourceNodes.length * targetNodes.length} relationship${sourceNodes.length * targetNodes.length !== 1 ? "s" : ""}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
