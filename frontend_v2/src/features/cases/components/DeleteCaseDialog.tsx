import { useEffect, useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { AlertTriangle } from "lucide-react"
import { useCaseDeletePreview, useDeleteCase } from "../hooks/use-cases"
import { useCaseManagementStore } from "../case-management.store"
import { describeCaseCounts } from "../api"
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
  const preview = useCaseDeletePreview(open ? caseToDelete?.id : undefined)
  const { selectedCaseId, setSelectedCaseId } = useCaseManagementStore()
  const [typed, setTyped] = useState("")

  useEffect(() => {
    if (!open) {
      setTyped("")
      deleteCase.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const title = caseToDelete?.title ?? ""
  const matches = typed.trim() === title.trim() && title.trim() !== ""
  // Deleted items switched on (the server says how long a restore stays possible); off, the delete is immediate.
  const days = preview.data?.restorable_days ?? null
  const kept = days !== null
  const counts = preview.data ? describeCaseCounts(preview.data.holds) : []

  const handleDelete = () => {
    if (!caseToDelete || !matches) return
    deleteCase.mutate(
      { caseId: caseToDelete.id, confirmTitle: typed },
      {
        onSuccess: () => {
          if (selectedCaseId === caseToDelete.id) {
            setSelectedCaseId(null)
          }
          onOpenChange(false)
        },
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm text-destructive">
            <AlertTriangle className="size-4" />
            Delete Case
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <p className="text-sm">
            {kept ? (
              <>
                <span className="font-semibold">{title}</span> will be moved to Deleted items.
              </>
            ) : (
              <>
                Are you sure you want to delete <span className="font-semibold">{title}</span>?
              </>
            )}
          </p>
          <div
            className={
              kept
                ? "rounded-md border border-amber-200 dark:border-amber-500/20 bg-amber-50 dark:bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-300 space-y-1.5"
                : "rounded-md border border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400 space-y-1.5"
            }
            data-testid="delete-case-summary"
          >
            {preview.isLoading ? (
              <p>Counting what this case holds…</p>
            ) : preview.isError ? (
              <p>What this case holds could not be counted.</p>
            ) : (
              <p>
                It holds{" "}
                {counts.length ? counts.join(", ") : "no evidence, ledger or phone records"}.
                {kept ? " All of it disappears from every screen, search and the agent at once." : ""}
              </p>
            )}
            {kept ? (
              <p>
                The case owner or an admin can restore it, exactly as it was, from Deleted items for{" "}
                {days} days. After that it is removed for good.
              </p>
            ) : (
              <p>
                This action is permanent. All case data, evidence files, snapshots, and graph data will be
                irreversibly deleted.
              </p>
            )}
          </div>
          <label className="block space-y-1 text-xs">
            <span>
              Type the case title to confirm: <span className="font-semibold">{title}</span>
            </span>
            <Input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={title}
              className="h-8 text-xs"
              aria-label="Case title to confirm"
              autoComplete="off"
            />
          </label>
          {deleteCase.isError && (
            <p className="text-xs text-destructive" role="alert">
              {deleteCase.error instanceof Error ? deleteCase.error.message : "The case could not be deleted."}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={handleDelete}
            disabled={deleteCase.isPending || !matches}
          >
            {deleteCase.isPending ? <LoadingSpinner size="sm" /> : kept ? "Move to Deleted items" : "Delete Case"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
