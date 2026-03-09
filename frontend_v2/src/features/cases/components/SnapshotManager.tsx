import { useState } from "react"
import { Camera, Trash2, Download, ChevronDown, ChevronRight, Clock } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useSnapshots, useDeleteSnapshot, useCreateSnapshot } from "../hooks/use-snapshots"
import type { Snapshot } from "../snapshots-api"

interface SnapshotManagerProps {
  caseId: string
  onLoad?: (snapshot: Snapshot) => void
}

export function SnapshotManager({ caseId, onLoad }: SnapshotManagerProps) {
  const { data: snapshots, isLoading } = useSnapshots()
  const deleteMutation = useDeleteSnapshot()
  const createMutation = useCreateSnapshot()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState("")
  const [newNotes, setNewNotes] = useState("")

  const caseSnapshots = snapshots?.filter((s) => s.case_id === caseId) ?? []

  const handleDelete = (id: string) => {
    deleteMutation.mutate(id)
  }

  const handleCreate = () => {
    createMutation.mutate(
      {
        name: newName,
        notes: newNotes || undefined,
        subgraph: {},
        case_id: caseId,
      },
      {
        onSuccess: () => {
          setShowCreate(false)
          setNewName("")
          setNewNotes("")
        },
      }
    )
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">Snapshots</h3>
        <Button variant="outline" size="sm" onClick={() => setShowCreate(true)}>
          <Camera className="size-3.5" />
          Save Snapshot
        </Button>
      </div>

      {caseSnapshots.length === 0 ? (
        <EmptyState
          icon={Camera}
          title="No snapshots"
          description="Save a snapshot to preserve the current graph state"
          className="py-6"
        />
      ) : (
        <div className="space-y-2">
          {caseSnapshots.map((snapshot) => (
            <Card key={snapshot.id} className="p-0">
              <div
                className="flex cursor-pointer items-center gap-2 px-3 py-2"
                onClick={() =>
                  setExpandedId(expandedId === snapshot.id ? null : snapshot.id)
                }
              >
                {expandedId === snapshot.id ? (
                  <ChevronDown className="size-3.5 text-muted-foreground" />
                ) : (
                  <ChevronRight className="size-3.5 text-muted-foreground" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{snapshot.name}</p>
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                    <Clock className="size-3" />
                    {new Date(snapshot.created_at).toLocaleString()}
                    <Badge variant="slate" className="text-[10px]">
                      {snapshot.node_count} nodes
                    </Badge>
                    <Badge variant="slate" className="text-[10px]">
                      {snapshot.link_count} links
                    </Badge>
                  </div>
                </div>
              </div>

              {expandedId === snapshot.id && (
                <CardContent className="border-t border-border px-3 py-2">
                  {snapshot.notes && (
                    <p className="mb-2 text-xs text-muted-foreground">
                      {snapshot.notes}
                    </p>
                  )}
                  {snapshot.ai_overview && (
                    <p className="mb-2 text-xs text-foreground">
                      {snapshot.ai_overview}
                    </p>
                  )}
                  <div className="flex gap-2">
                    {onLoad && (
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => onLoad(snapshot)}
                      >
                        <Download className="size-3.5" />
                        Load
                      </Button>
                    )}
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => handleDelete(snapshot.id)}
                      disabled={deleteMutation.isPending}
                    >
                      <Trash2 className="size-3.5" />
                      Delete
                    </Button>
                  </div>
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      )}

      {/* Create Snapshot Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save Snapshot</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs font-medium">Name</label>
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Pre-merge analysis"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">Notes (optional)</label>
              <Textarea
                value={newNotes}
                onChange={(e) => setNewNotes(e.target.value)}
                placeholder="Any notes about this snapshot..."
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleCreate}
              disabled={!newName || createMutation.isPending}
            >
              {createMutation.isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
