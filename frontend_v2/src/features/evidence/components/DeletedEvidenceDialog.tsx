import { useState } from "react"
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
import { useDeletedItemAction, useDeletedItems } from "../hooks/use-evidence-detail"
import type { DeletedItem, PurgeResult } from "../api"
import { purgeSummary, size } from "../deleted-items"

interface DeletedEvidenceDialogProps {
  caseId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

function when(iso: string | null) {
  if (!iso) return "an unknown time"
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
}

/** Deleted items of the case: everything deleted (files, folders, casework, links, ...), who deleted it, when, days
 * left, Restore and Delete now. */
export function DeletedEvidenceDialog({ caseId, open, onOpenChange }: DeletedEvidenceDialogProps) {
  const deleted = useDeletedItems(caseId, open)
  const restore = useDeletedItemAction(caseId, "restore")
  const purge = useDeletedItemAction(caseId, "purge")
  const [confirming, setConfirming] = useState<string | null>(null)
  const rows = deleted.data?.items ?? []
  const days = deleted.data?.retention_days ?? 30
  const canManage = deleted.data?.can_manage ?? false
  const busy = restore.isPending || purge.isPending
  const key = (row: DeletedItem) => `${row.kind}:${row.id}`
  const error = restore.error ?? purge.error

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <Trash2 className="size-4" />
            Deleted items
          </DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          Anything deleted in this case is kept here for {days} days, hidden from every screen, search and the
          agent, then removed for good. Restore brings it back exactly as it was, with everything that hung off it.
          {canManage ? "" : " Only the case owner or an admin can restore or remove items."}
        </p>
        <div className="max-h-[60vh] overflow-auto" data-testid="deleted-items">
          {deleted.isLoading ? (
            <div className="flex justify-center py-6">
              <LoadingSpinner size="sm" />
            </div>
          ) : deleted.isError ? (
            <p className="py-4 text-xs text-destructive">Deleted items could not be loaded.</p>
          ) : rows.length === 0 ? (
            <p className="py-4 text-xs text-muted-foreground">Nothing deleted in this case.</p>
          ) : (
            <ul className="divide-y text-xs">
              {rows.map((row) => (
                <li key={key(row)} className="flex items-start justify-between gap-3 py-2.5" data-kind={row.kind}>
                  <div className="min-w-0 space-y-0.5">
                    <p className="truncate">
                      <span className="text-muted-foreground">{row.kind_label} · </span>
                      <span className="font-semibold">{row.label ?? "(untitled)"}</span>
                    </p>
                    <p className="text-muted-foreground">
                      Deleted {when(row.deleted_at)} by {row.deleted_by?.name ?? row.deleted_by?.email ?? "an unknown person"}
                      {row.size ? ` · ${size(row.size)}` : ""}
                    </p>
                    {row.detail && <p className="text-muted-foreground">{row.detail}</p>}
                    {row.days_left !== null && (
                      <p className={row.days_left <= 3 ? "text-destructive" : "text-muted-foreground"}>
                        {row.days_left} {row.days_left === 1 ? "day" : "days"} left to restore (removed for good{" "}
                        {when(row.purge_at)})
                      </p>
                    )}
                  </div>
                  {row.can_restore && (
                    <div className="flex shrink-0 gap-1.5">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy}
                        onClick={() =>
                          restore.mutate(
                            { kind: row.kind, id: row.id },
                            { onSuccess: () => toast.success(`Restored ${row.label ?? row.kind_label}`) }
                          )
                        }
                      >
                        {restore.isPending && restore.variables?.id === row.id ? <LoadingSpinner size="sm" /> : "Restore"}
                      </Button>
                      <Button
                        size="sm"
                        variant={confirming === key(row) ? "danger" : "ghost"}
                        disabled={busy}
                        onClick={() => {
                          if (confirming !== key(row)) {
                            setConfirming(key(row))
                            return
                          }
                          setConfirming(null)
                          purge.mutate(
                            { kind: row.kind, id: row.id },
                            {
                              onSuccess: (out) => {
                                const done = out as PurgeResult
                                toast.success(purgeSummary(done.label, done.counts), { duration: 12000 })
                              },
                            }
                          )
                        }}
                      >
                        {purge.isPending && purge.variables?.id === row.id ? (
                          <LoadingSpinner size="sm" />
                        ) : confirming === key(row) ? (
                          "Remove for good?"
                        ) : (
                          "Delete now"
                        )}
                      </Button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
          {error && (
            <p className="pt-2 text-xs text-destructive" role="alert">
              {error instanceof Error ? error.message : "That could not be done."}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
