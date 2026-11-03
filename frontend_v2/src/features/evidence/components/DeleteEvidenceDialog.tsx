import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { AlertTriangle } from "lucide-react"

interface DeleteEvidenceDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  fileCount: number
  onConfirm: (deleteExclusiveEntities: boolean) => void
  isPending?: boolean
}

export function DeleteEvidenceDialog({
  open,
  onOpenChange,
  fileCount,
  onConfirm,
  isPending,
}: DeleteEvidenceDialogProps) {
  const [deleteEntities, setDeleteEntities] = useState(false)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="size-4 text-red-600 dark:text-red-400" />
            Delete Evidence
          </DialogTitle>
          <DialogDescription>
            {fileCount} file{fileCount !== 1 ? "s" : ""} will be moved to Deleted items and disappear from every
            screen, search and the agent. The case owner or an admin can restore{" "}
            {fileCount !== 1 ? "them" : "it"} exactly as before for 30 days; after that{" "}
            {fileCount !== 1 ? "they are" : "it is"} removed for good.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <label className="flex items-start gap-3 rounded-md border border-border p-3 cursor-pointer hover:bg-muted/50">
            <Checkbox
              checked={deleteEntities}
              onCheckedChange={(checked) => setDeleteEntities(checked === true)}
              className="mt-0.5"
            />
            <div>
              <p className="text-sm font-medium text-foreground">
                Also hide exclusive entities
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Hide the entities and relationships found only in these files (they come back with a restore)
              </p>
            </div>
          </label>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={() => onConfirm(deleteEntities)}
            disabled={isPending}
          >
            {isPending ? "Moving..." : "Move to Deleted items"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
