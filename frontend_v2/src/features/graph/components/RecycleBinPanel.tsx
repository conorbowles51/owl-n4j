import { useCallback, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { NodeBadge } from "@/components/ui/node-badge"
import { Trash2, RotateCcw, AlertTriangle } from "lucide-react"
import { graphAPI } from "../api"
import type { RecycledEntity } from "@/types/graph.types"

interface RecycleBinPanelProps {
  caseId: string
}

function reasonLabel(reason: string) {
  if (reason === "merged") return "Merged"
  if (reason === "merge") return "Merged"
  if (reason?.startsWith("merge_into:")) return "Merged"
  if (reason?.startsWith("file_delete:")) return "Evidence removed"
  if (reason === "manual_delete") return "Deleted"
  return "Deleted"
}

function reasonDetail(entity: RecycledEntity) {
  if (entity.reason === "merged") {
    return "Merged into a new entity"
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
    <div className="flex h-full flex-col p-4">
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
          description="Deleted entities will appear here"
          className="py-8"
        />
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto pr-1">
          <div className="space-y-4">
            {Object.entries(grouped).map(([label, items]) => (
              <div key={label} className="space-y-2">
                <div className="text-[10px] font-semibold uppercase text-muted-foreground">
                  {label} ({items.length})
                </div>
                {items.map((entity) => {
                  const detail = reasonDetail(entity)
                  const isConfirming = confirmDeleteKey === entity.key

                  return (
                    <div key={entity.key} className="rounded-lg border p-2">
                      <div className="flex items-start gap-2">
                        <NodeBadge type={entity.type} />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs font-medium">
                            {entity.original_name}
                          </p>
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
                            {entity.relationship_count} relationship
                            {entity.relationship_count === 1 ? "" : "s"} archived
                          </p>
                        </div>
                        <div className="flex shrink-0 gap-1">
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() =>
                              runAction(entity.key, () =>
                                restoreMutation.mutateAsync(entity.key)
                              )
                            }
                            disabled={actionKey === entity.key}
                            title="Restore"
                          >
                            <RotateCcw className="size-3.5" />
                          </Button>
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
                              runAction(entity.key, () =>
                                deleteMutation.mutateAsync(entity.key)
                              )
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
        </div>
      )}
    </div>
  )
}
