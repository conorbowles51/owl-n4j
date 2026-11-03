import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { Trash2 } from "lucide-react"
import { toast } from "sonner"
import { useDeletedEvidence, useRestoreEvidence } from "../hooks/use-evidence-detail"

interface DeletedEvidenceDialogProps {
  caseId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

function when(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
}

function size(bytes: number) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} bytes`
}

/** Deleted items of the case's Evidence: who deleted each file, when, what it holds, days left, Restore. */
export function DeletedEvidenceDialog({ caseId, open, onOpenChange }: DeletedEvidenceDialogProps) {
  const deleted = useDeletedEvidence(caseId, open)
  const restore = useRestoreEvidence(caseId)
  const rows = deleted.data?.files ?? []
  const days = deleted.data?.retention_days ?? 30
  const canRestore = deleted.data?.can_restore ?? false

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <Trash2 className="size-4" />
            Deleted evidence files
          </DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          A deleted file is kept here for {days} days, hidden from every screen, search and the agent. Restore
          brings back the file, its text search and its graph exactly as they were.
          {canRestore ? "" : " Only the case owner or an admin can restore."}
        </p>
        <div className="max-h-[60vh] overflow-auto" data-testid="deleted-evidence">
          {deleted.isLoading ? (
            <div className="flex justify-center py-6">
              <LoadingSpinner size="sm" />
            </div>
          ) : deleted.isError ? (
            <p className="py-4 text-xs text-destructive">Deleted files could not be loaded.</p>
          ) : rows.length === 0 ? (
            <p className="py-4 text-xs text-muted-foreground">No deleted files in this case.</p>
          ) : (
            <ul className="divide-y text-xs">
              {rows.map((row) => (
                <li key={row.id} className="flex items-start justify-between gap-3 py-2.5">
                  <div className="min-w-0 space-y-0.5">
                    <p className="font-semibold truncate">{row.filename}</p>
                    <p className="text-muted-foreground">
                      Deleted {when(row.deleted_at)} by {row.deleted_by?.name ?? "an unknown person"} · {size(row.size)}
                    </p>
                    <p className="text-muted-foreground">
                      Holds {row.holds.text_chunks} text passages and {row.holds.entities_only_in_this_file}{" "}
                      {row.holds.entities_only_in_this_file === 1 ? "entity" : "entities"} found only in this file
                    </p>
                    <p className={row.days_left <= 3 ? "text-destructive" : "text-muted-foreground"}>
                      {row.days_left} {row.days_left === 1 ? "day" : "days"} left to restore (removed for good{" "}
                      {when(row.purge_at)})
                    </p>
                  </div>
                  {canRestore && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={restore.isPending}
                      onClick={() =>
                        restore.mutate(row.id, {
                          onSuccess: (out) =>
                            toast.success(
                              `Restored ${out.filename}` +
                                (out.merged_entities.length
                                  ? ` (${out.merged_entities.length} entity merged with one made since)`
                                  : "")
                            ),
                        })
                      }
                    >
                      {restore.isPending && restore.variables === row.id ? <LoadingSpinner size="sm" /> : "Restore"}
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {restore.isError && (
            <p className="pt-2 text-xs text-destructive" role="alert">
              {restore.error instanceof Error ? restore.error.message : "The file could not be restored."}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
