import { useState } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { nodeColors } from "@/lib/theme"
import { graphAPI } from "../api"

interface AddNodeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
  onCreated?: (key: string) => void
}

const entityTypes = Object.keys(nodeColors)

export function AddNodeDialog({ open, onOpenChange, caseId, onCreated }: AddNodeDialogProps) {
  const [name, setName] = useState("")
  const [type, setType] = useState("person")
  const [summary, setSummary] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleCreate = async () => {
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      const result = await graphAPI.createNode(
        { name, type, summary: summary || undefined, case_id: caseId },
        caseId
      )
      if (!result.success) {
        setError(result.error || "The entity was not created.")
        return
      }
      onCreated?.(result.node_key)
      onOpenChange(false)
      setName("")
      setSummary("")
    } catch (err) {
      setError(err instanceof Error ? err.message : "The entity was not created.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add Entity</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium">Name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Entity name" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Type</label>
            <Select value={type} onValueChange={setType}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {entityTypes.map((t) => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Summary (optional)</label>
            <Textarea value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="Brief description..." />
          </div>
          {error && (
            <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" onClick={handleCreate} disabled={!name.trim() || saving}>
            {saving ? "Creating..." : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
