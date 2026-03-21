import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { AlertTriangle } from "lucide-react"

interface DeleteFolderDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  folderName: string
  fileCount: number
  onConfirm: () => void
  isPending?: boolean
}

export function DeleteFolderDialog({
  open,
  onOpenChange,
  folderName,
  fileCount,
  onConfirm,
  isPending,
}: DeleteFolderDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="size-5 text-red-500" />
            Delete Folder
          </DialogTitle>
          <DialogDescription>
            Are you sure you want to delete <strong>{folderName}</strong>?
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {fileCount > 0 && (
            <div className="rounded-md border border-red-500/20 bg-red-500/5 p-3 text-sm">
              <p className="font-medium text-red-600 dark:text-red-400">
                {fileCount} file{fileCount !== 1 ? "s" : ""} will be permanently deleted from disk and database.
              </p>
            </div>
          )}
          <div className="rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-sm">
            <p className="text-amber-700 dark:text-amber-400">
              Graph data (entities, relationships) extracted from these files will be preserved in Neo4j.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={onConfirm}
            disabled={isPending}
          >
            {isPending ? "Deleting..." : "Delete Folder"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
