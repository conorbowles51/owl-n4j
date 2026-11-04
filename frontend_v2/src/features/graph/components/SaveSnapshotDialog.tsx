import { useState } from "react"
import { Camera, Loader2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useCreateSnapshot } from "@/features/cases/hooks/use-snapshots"
import type { GraphData } from "@/types/graph.types"
import { buildSnapshotSubgraph, readCanvasGraph } from "../lib/graph-snapshot"

interface SaveSnapshotDialogProps {
  caseId: string
  shown: GraphData
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Saves what is on the graph now as a snapshot of this case: the entities and links on screen, where each sits, and
 * (worked out on the server) the dated events among them. The saved counts are reported back as the server stored
 * them, so the investigator sees exactly what the snapshot holds.
 */
export function SaveSnapshotDialog({ caseId, shown, open, onOpenChange }: SaveSnapshotDialogProps) {
  const [name, setName] = useState("")
  const [notes, setNotes] = useState("")
  const create = useCreateSnapshot()
  const nodeCount = shown.nodes.length

  const save = () => {
    const subgraph = buildSnapshotSubgraph(shown, readCanvasGraph())
    const startedAt = performance.now()
    create.mutate(
      { name: name.trim(), notes: notes.trim(), subgraph, case_id: caseId },
      {
        onSuccess: (saved) => {
          const seconds = ((performance.now() - startedAt) / 1000).toFixed(1)
          toast.success(
            `Snapshot saved: ${saved.node_count} entities, ${saved.link_count} links, ${saved.timeline_count ?? 0} events (${seconds} s)`,
          )
          setName("")
          setNotes("")
          onOpenChange(false)
        },
        onError: (error) => toast.error(`Snapshot not saved: ${error instanceof Error ? error.message : String(error)}`),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !create.isPending && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Save snapshot</DialogTitle>
          <DialogDescription>
            Keeps the {nodeCount} {nodeCount === 1 ? "entity" : "entities"} on the graph now, where each sits, and the
            dated events among them. Its report prints only these.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <label htmlFor="snapshot-name" className="text-xs font-medium">Name</label>
            <Input id="snapshot-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Payments to Acme, March" />
          </div>
          <div className="space-y-1">
            <label htmlFor="snapshot-notes" className="text-xs font-medium">Notes (optional)</label>
            <Textarea id="snapshot-notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={4} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={create.isPending}>Cancel</Button>
          <Button onClick={save} disabled={!name.trim() || nodeCount === 0 || create.isPending}>
            {create.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Camera className="size-3.5" />}
            {create.isPending ? "Saving…" : "Save snapshot"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
