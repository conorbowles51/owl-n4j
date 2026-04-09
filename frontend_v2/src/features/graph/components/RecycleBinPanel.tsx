import { useCallback, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { NodeBadge } from "@/components/ui/node-badge"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Trash2, RotateCcw, AlertTriangle, GitMerge } from "lucide-react"
import { graphAPI } from "../api"
import type { RecycledEntity } from "@/types/graph.types"

interface RecycleBinPanelProps {
  caseId: string
}

function reasonLabel(reason: string) {
  if (reason === "merge") return "Undo merge"
  if (reason?.startsWith("merge_into:")) return "Merged"
  if (reason?.startsWith("file_delete:")) return "Evidence removed"
  if (reason === "manual_delete") return "Deleted"
  return "Deleted"
}

function reasonDetail(entity: RecycledEntity) {
  if (entity.item_type === "merge_undo") {
    const names = entity.source_names?.filter(Boolean).join(", ")
    return names ? `Merged with ${names}` : null
  }
  if (entity.reason?.startsWith("merge_into:")) {
    return `Merged into ${entity.reason.slice("merge_into:".length)}`
  }
  if (entity.reason?.startsWith("file_delete:")) {
    return `Evidence removed: ${entity.reason.slice("file_delete:".length)}`
  }
  return null
}

export function RecycleBinPanel({ caseId }: RecycleBinPanelProps) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [actionKey, setActionKey] = useState<string | null>(null)
  const [confirmDeleteKey, setConfirmDeleteKey] = useState<string | null>(null)
  const [undoItem, setUndoItem] = useState<RecycledEntity | null>(null)

  const recycleQueryKey = ["graph", "recycle-bin", caseId]
  const { data, isLoading, error: loadError } = useQuery({
    queryKey: recycleQueryKey,
    queryFn: () => graphAPI.listRecycledEntities(caseId),
  })
  const entities = data?.items ?? []

  const refreshGraph = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["graph", caseId] })
    queryClient.invalidateQueries({ queryKey: ["graph", "summary", caseId] })
    queryClient.invalidateQueries({ queryKey: ["graph", "entity-types", caseId] })
    queryClient.invalidateQueries({ queryKey: recycleQueryKey })
  }, [caseId, queryClient, recycleQueryKey])

  const restoreMutation = useMutation({
    mutationFn: (key: string) => graphAPI.restoreRecycledEntity(key, caseId),
    onSuccess: refreshGraph,
  })

  const undoMutation = useMutation({
    mutationFn: ({ key, keepMergedNode }: { key: string; keepMergedNode: boolean }) =>
      graphAPI.undoMerge(key, caseId, keepMergedNode),
    onSuccess: () => {
      setUndoItem(null)
      refreshGraph()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (key: string) => graphAPI.permanentlyDeleteRecycled(key, caseId),
    onSuccess: () => {
      setConfirmDeleteKey(null)
      refreshGraph()
    },
  })

  const grouped = useMemo(() => {
    return entities.reduce<Record<string, RecycledEntity[]>>((acc, entity) => {
      const label = reasonLabel(entity.reason)
      acc[label] = acc[label] ?? []
      acc[label].push(entity)
      return acc
    }, {})
  }, [entities])

  const runAction = async (key: string, action: () => Promise<unknown>) => {
    setActionKey(key)
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Recycle bin action failed")
    } finally {
      setActionKey(null)
    }
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <LoadingSpinner />
      </div>
    )
  }

  const visibleError = error ?? (loadError instanceof Error ? loadError.message : null)

  return (
    <div className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold">Recycle Bin</h3>
        <Badge variant="slate">{entities.length} items</Badge>
      </div>

      {visibleError && (
        <div className="mb-3 flex gap-2 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          <span>{visibleError}</span>
        </div>
      )}

      {entities.length === 0 ? (
        <EmptyState
          icon={Trash2}
          title="Recycle bin is empty"
          description="Deleted and merged entities will appear here"
          className="py-8"
        />
      ) : (
        <ScrollArea className="max-h-[440px]">
          <div className="space-y-4">
            {Object.entries(grouped).map(([label, items]) => (
              <div key={label} className="space-y-2">
                <div className="text-[10px] font-semibold uppercase text-muted-foreground">
                  {label} ({items.length})
                </div>
                {items.map((entity) => {
                  const isMergeUndo = entity.item_type === "merge_undo"
                  const detail = reasonDetail(entity)
                  const isConfirming = confirmDeleteKey === entity.key
                  const title = isMergeUndo
                    ? entity.title ?? entity.merged_name ?? "Merged entities"
                    : entity.original_name

                  return (
                    <div key={entity.key} className="rounded-lg border p-2">
                      <div className="flex items-start gap-2">
                        {isMergeUndo ? (
                          <GitMerge className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
                        ) : (
                          <NodeBadge type={entity.type} />
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs font-medium">{title}</p>
                          {isMergeUndo && entity.merged_name && (
                            <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
                              Result: {entity.merged_name}
                            </p>
                          )}
                          <p className="text-[10px] text-muted-foreground">
                            {new Date(entity.deleted_at).toLocaleString()}
                            {entity.deleted_by ? ` by ${entity.deleted_by}` : ""}
                          </p>
                          {detail && (
                            <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
                              {detail}
                            </p>
                          )}
                          <p className="mt-0.5 text-[10px] text-muted-foreground">
                            {isMergeUndo
                              ? `${entity.source_count ?? entity.source_names?.length ?? 0} merged node${
                                  (entity.source_count ?? entity.source_names?.length ?? 0) === 1 ? "" : "s"
                                }, ${entity.relationship_count} relationship${
                                  entity.relationship_count === 1 ? "" : "s"
                                } archived`
                              : `${entity.relationship_count} relationship${
                                  entity.relationship_count === 1 ? "" : "s"
                                } archived`}
                          </p>
                        </div>
                        <div className="flex shrink-0 gap-1">
                          {isMergeUndo ? (
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              onClick={() => setUndoItem(entity)}
                              disabled={actionKey === entity.key}
                              title="Undo merge"
                            >
                              <RotateCcw className="size-3.5" />
                            </Button>
                          ) : (
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              onClick={() =>
                                runAction(entity.key, () => restoreMutation.mutateAsync(entity.key))
                              }
                              disabled={actionKey === entity.key}
                              title="Restore"
                            >
                              <RotateCcw className="size-3.5" />
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => setConfirmDeleteKey(entity.key)}
                            disabled={actionKey === entity.key}
                            title="Delete permanently"
                            className="text-red-600 hover:text-red-500 dark:text-red-400"
                          >
                            <Trash2 className="size-3.5" />
                          </Button>
                        </div>
                      </div>
                      {isConfirming && (
                        <div className="mt-2 flex items-center justify-end gap-2 border-t pt-2">
                          <span className="text-[10px] text-muted-foreground">
                            Delete forever?
                          </span>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setConfirmDeleteKey(null)}
                            disabled={actionKey === entity.key}
                          >
                            Cancel
                          </Button>
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() =>
                              runAction(entity.key, () => deleteMutation.mutateAsync(entity.key))
                            }
                            disabled={actionKey === entity.key}
                          >
                            {actionKey === entity.key ? "Deleting..." : "Delete"}
                          </Button>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </ScrollArea>
      )}

      <Dialog open={!!undoItem} onOpenChange={(open) => !open && setUndoItem(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Undo merge</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 text-sm">
            <p>
              Restore the original nodes from this merge
              {undoItem?.merged_name ? ` and keep ${undoItem.merged_name}?` : "?"}
            </p>
            <p className="text-xs text-muted-foreground">
              Keeping the merged node preserves anything added after the merge.
            </p>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setUndoItem(null)}
              disabled={!!actionKey}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() =>
                undoItem &&
                runAction(undoItem.key, () =>
                  undoMutation.mutateAsync({ key: undoItem.key, keepMergedNode: false })
                )
              }
              disabled={!!actionKey}
            >
              Restore and delete merged node
            </Button>
            <Button
              variant="primary"
              onClick={() =>
                undoItem &&
                runAction(undoItem.key, () =>
                  undoMutation.mutateAsync({ key: undoItem.key, keepMergedNode: true })
                )
              }
              disabled={!!actionKey}
            >
              Restore and keep merged node
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
