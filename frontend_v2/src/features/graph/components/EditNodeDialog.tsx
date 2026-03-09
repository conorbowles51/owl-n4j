import { useState, useEffect } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { NodeBadge } from "@/components/ui/node-badge"
import type { GraphNode } from "@/types/graph.types"
import { graphAPI } from "../api"

interface EditNodeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  node: GraphNode | null
  caseId: string
  onSaved?: () => void
}

export function EditNodeDialog({ open, onOpenChange, node, caseId, onSaved }: EditNodeDialogProps) {
  const [name, setName] = useState("")
  const [summary, setSummary] = useState("")
  const [notes, setNotes] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (node) {
      setName(node.label)
      setSummary(String(node.summary ?? node.properties.summary ?? ""))
      setNotes(String(node.notes ?? node.properties.notes ?? ""))
    }
  }, [node])

  const handleSave = async () => {
    if (!node) return
    setSaving(true)
    try {
      await graphAPI.updateNode(node.key, { name, summary: summary || undefined, notes: notes || undefined, case_id: caseId })
      onSaved?.()
      onOpenChange(false)
    } finally {
      setSaving(false)
    }
  }

  if (!node) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <NodeBadge type={node.type} />
            Edit Entity
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium">Name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Summary</label>
            <Textarea value={summary} onChange={(e) => setSummary(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Notes</label>
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" onClick={handleSave} disabled={!name.trim() || saving}>
            {saving ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
