import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { AlertTriangle } from "lucide-react"
import { useDeleteCase } from "../hooks/use-cases"
import { useCaseManagementStore } from "../case-management.store"
import type { Case } from "@/types/case.types"

interface DeleteCaseDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseToDelete: Case | null
}

export function DeleteCaseDialog({
  open,
  onOpenChange,
  caseToDelete,
}: DeleteCaseDialogProps) {
  const deleteCase = useDeleteCase()
  const { selectedCaseId, setSelectedCaseId } = useCaseManagementStore()

  const handleDelete = () => {
    if (!caseToDelete) return
    deleteCase.mutate(caseToDelete.id, {
      onSuccess: () => {
        if (selectedCaseId === caseToDelete.id) {
          setSelectedCaseId(null)
        }
        onOpenChange(false)
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm text-destructive">
            <AlertTriangle className="size-4" />
            Delete Case
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <p className="text-sm">
            Are you sure you want to delete{" "}
            <span className="font-semibold">{caseToDelete?.title}</span>?
          </p>
          <div className="rounded-md border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
            This action is permanent. All case data, evidence files, snapshots,
            and graph data will be irreversibly deleted.
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={handleDelete}
            disabled={deleteCase.isPending}
          >
            {deleteCase.isPending ? (
              <LoadingSpinner size="sm" />
            ) : (
              "Delete Case"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
