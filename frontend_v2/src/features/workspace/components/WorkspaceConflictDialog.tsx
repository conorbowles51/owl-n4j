import { AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface WorkspaceConflictDialogProps {
  open: boolean
  itemLabel: string
  localSummary: string
  serverSummary: string
  onMerge: () => void
  onReload: () => void
}

export function WorkspaceConflictDialog({
  open,
  itemLabel,
  localSummary,
  serverSummary,
  onMerge,
  onReload,
}: WorkspaceConflictDialogProps) {
  return (
    <Dialog open={open}>
      <DialogContent className="max-w-2xl" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <AlertTriangle className="size-4 text-amber-500" />
            {itemLabel} changed elsewhere
          </DialogTitle>
          <DialogDescription>
            Another saved version exists. Compare both copies, then reload the
            saved version or keep your draft open to merge manually.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="min-w-0 rounded-md border border-border p-3">
            <p className="mb-2 text-[10px] font-semibold uppercase text-muted-foreground">
              Your unsaved draft
            </p>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-sans text-xs">
              {localSummary || "No local content"}
            </pre>
          </div>
          <div className="min-w-0 rounded-md border border-border p-3">
            <p className="mb-2 text-[10px] font-semibold uppercase text-muted-foreground">
              Current saved version
            </p>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-sans text-xs">
              {serverSummary || "No saved content"}
            </pre>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onReload}>
            Reload saved version
          </Button>
          <Button onClick={onMerge}>Merge manually</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
