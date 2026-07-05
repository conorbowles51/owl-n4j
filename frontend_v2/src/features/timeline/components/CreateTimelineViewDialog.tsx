import { useState } from "react"
import { BookmarkPlus } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useCreateTimelineView } from "../hooks/use-timeline-views"
import type { TimelineView } from "../api"

interface CreateTimelineViewDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
  eventKeys: string[]
  filterSnapshot: Record<string, unknown>
  onCreated: (view: TimelineView) => void
}

export function CreateTimelineViewDialog({
  open,
  onOpenChange,
  caseId,
  eventKeys,
  filterSnapshot,
  onCreated,
}: CreateTimelineViewDialogProps) {
  const defaultTitle = `Focused timeline ${new Date().toISOString().slice(0, 10)}`
  const [title, setTitle] = useState(defaultTitle)
  const [description, setDescription] = useState("")
  const createView = useCreateTimelineView()

  const handleCreate = () => {
    const trimmedTitle = title.trim()
    if (!trimmedTitle || eventKeys.length === 0) return
    createView.mutate(
      {
        case_id: caseId,
        title: trimmedTitle,
        description: description.trim() || null,
        event_keys: eventKeys,
        filter_snapshot: filterSnapshot,
        export_defaults: {
          fields: {
            source_references: true,
            notebook_notes: false,
          },
        },
      },
      {
        onSuccess: (view) => {
          toast.success("Timeline view saved")
          onCreated(view)
          onOpenChange(false)
          setTitle(defaultTitle)
          setDescription("")
        },
        onError: (error) => {
          toast.error(error instanceof Error ? error.message : "Failed to save timeline view")
        },
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <BookmarkPlus className="size-4" />
            Save Timeline View
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium">Title</label>
            <Input value={title} onChange={(event) => setTitle(event.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium">Description</label>
            <Textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
              placeholder="Optional"
            />
          </div>
          <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            {eventKeys.length} event{eventKeys.length === 1 ? "" : "s"} will be saved.
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleCreate}
            disabled={!title.trim() || eventKeys.length === 0 || createView.isPending}
          >
            Save View
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
