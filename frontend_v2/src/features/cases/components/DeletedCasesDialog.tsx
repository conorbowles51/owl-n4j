import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { Trash2 } from "lucide-react"
import { useDeletedCases, useRestoreCase } from "../hooks/use-cases"
import { describeCaseCounts } from "../api"

interface DeletedCasesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

function when(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
}

/** Deleted items for cases: the cases this person can restore (their own; all of them for an admin). */
export function DeletedCasesDialog({ open, onOpenChange }: DeletedCasesDialogProps) {
  const deleted = useDeletedCases(open)
  const restore = useRestoreCase()
  const rows = deleted.data?.cases ?? []
  const days = deleted.data?.retention_days ?? 30

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <Trash2 className="size-4" />
            Deleted cases
          </DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          A deleted case is kept here for {days} days, hidden everywhere. Restore brings it back exactly as it
          was. After {days} days it is removed for good.
        </p>
        <div className="max-h-[60vh] overflow-auto" data-testid="deleted-cases">
          {deleted.isLoading ? (
            <div className="flex justify-center py-6">
              <LoadingSpinner size="sm" />
            </div>
          ) : deleted.isError ? (
            <p className="py-4 text-xs text-destructive">Deleted cases could not be loaded.</p>
          ) : rows.length === 0 ? (
            <p className="py-4 text-xs text-muted-foreground">No deleted cases you can restore.</p>
          ) : (
            <ul className="divide-y text-xs">
              {rows.map((row) => (
                <li key={row.id} className="flex items-start justify-between gap-3 py-2.5">
                  <div className="min-w-0 space-y-0.5">
                    <p className="font-semibold truncate">{row.title}</p>
                    <p className="text-muted-foreground">
                      Deleted {when(row.deleted_at)} by {row.deleted_by?.name ?? "an unknown person"}
                      {row.owner ? ` · owner ${row.owner.name}` : ""}
                    </p>
                    <p className="text-muted-foreground">
                      {describeCaseCounts(row.holds).join(", ") || "No evidence, ledger or phone records"}
                    </p>
                    <p className={row.days_left <= 3 ? "text-destructive" : "text-muted-foreground"}>
                      {row.days_left} {row.days_left === 1 ? "day" : "days"} left to restore (removed for good{" "}
                      {when(row.purge_at)})
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={restore.isPending}
                    onClick={() => restore.mutate(row.id)}
                  >
                    {restore.isPending && restore.variables === row.id ? <LoadingSpinner size="sm" /> : "Restore"}
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {restore.isError && (
            <p className="pt-2 text-xs text-destructive" role="alert">
              {restore.error instanceof Error ? restore.error.message : "The case could not be restored."}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
