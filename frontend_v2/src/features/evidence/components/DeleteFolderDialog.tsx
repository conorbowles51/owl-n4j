import { useQuery } from "@tanstack/react-query"
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
import { foldersAPI } from "../folders.api"
import { describeFolderDelete } from "../folder-delete"

interface DeleteFolderDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
  folderId: string | null
  folderName: string
  onConfirm: () => void
  isPending?: boolean
  /** Why the last delete was refused (shown in the dialog; the folder is kept). */
  error?: string | null
}

export function DeleteFolderDialog({
  open,
  onOpenChange,
  caseId,
  folderId,
  folderName,
  onConfirm,
  isPending,
  error,
}: DeleteFolderDialogProps) {
  const summary = useQuery({
    queryKey: ["evidence-folder-delete-summary", caseId, folderId],
    queryFn: () => foldersAPI.deleteSummary(folderId!, caseId),
    enabled: open && !!folderId,
    staleTime: 0,
    gcTime: 0,
    retry: false,
  })
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
          <div className="rounded-md border border-red-500/20 bg-red-500/5 p-3 text-sm" role="status">
            <p className="font-medium text-red-600 dark:text-red-400">
              {summary.data
                ? describeFolderDelete(summary.data)
                : summary.isError
                  ? "The files in this folder could not be counted, so it cannot be deleted now. Close this and try again."
                  : "Counting the files in this folder and its subfolders…"}
            </p>
          </div>
          <div className="rounded-md border border-primary/20 bg-primary/5 p-3 text-sm">
            <p className="text-primary">
              Graph data (entities, relationships) found only in these files is hidden with them and comes back
              with a restore.
            </p>
          </div>
          {error && (
            <p role="alert" className="rounded-md border border-destructive/30 p-3 text-sm text-destructive">
              {error}
            </p>
          )}
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
            disabled={isPending || !summary.data}
          >
            {isPending ? "Deleting..." : "Delete Folder"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
