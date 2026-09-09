import type { FolderTreeNode } from "@/types/evidence.types"
import { useMemo, useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Folder, Home } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useCase } from "@/features/cases/hooks/use-cases"
import { useCasePermissions } from "@/features/cases/hooks/use-case-permissions"
import { useFolderTree } from "../hooks/use-folder-tree"
import {
  EvidenceMovesContext,
  EVIDENCE_DRAG_TYPE,
} from "../hooks/use-evidence-moves"
import {
  flattenFolders,
  invalidMoveReason,
  type MoveSource,
} from "../utils/move-targets"
import { foldersAPI } from "../folders.api"
import { useEvidenceStore } from "../evidence.store"

export function EvidenceMoveProvider({
  caseId,
  children,
}: {
  caseId: string
  children: React.ReactNode
}) {
  const { data: selectedCase } = useCase(caseId)
  const { canUploadEvidence } = useCasePermissions(selectedCase)
  const tree = useFolderTree(caseId)
  const folders = useMemo(() => flattenFolders(tree.data ?? []), [tree.data])
  const [request, setRequest] = useState<MoveSource | null>(null)
  const [destination, setDestination] = useState<string | null | undefined>(
    undefined
  )
  const [dragging, setDragging] = useState<MoveSource | null>(null)
  const inFlight = useRef(false)
  const qc = useQueryClient()
  const mutation = useMutation({
    mutationFn: async ({
      source,
      target,
    }: {
      source: MoveSource
      target: string | null
    }) => {
      if (source.kind === "folder") return foldersAPI.move(source.id, target)
      if (source.files.length === 1)
        return foldersAPI.moveFile(source.files[0].id, target)
      return foldersAPI.moveFilesBatch(
        source.files.map((file) => file.id),
        target
      )
    },
    onSuccess: async (result, { source }) => {
      if (source.kind === "files") {
        const movedIds = new Set(source.files.map((file) => file.id))
        useEvidenceStore.setState((state) => ({
          selectedFileIds: new Set(
            [...state.selectedFileIds].filter((id) => !movedIds.has(id))
          ),
        }))
      }
      setRequest(null)
      const count = result.moved
      toast.success(
        count === 0
          ? "Already in the selected folder"
          : `Moved ${count ?? 1} ${source.kind === "folder" ? "folder" : count === 1 ? "file" : "files"}`
      )
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] }),
        qc.invalidateQueries({
          queryKey: ["evidence-folder-contents", caseId],
        }),
        qc.invalidateQueries({ queryKey: ["evidence", caseId] }),
        qc.invalidateQueries({ queryKey: ["evidence-file"] }),
        qc.invalidateQueries({ queryKey: ["evidence-effective-profile"] }),
      ])
      const state = useEvidenceStore.getState()
      if (
        source.kind === "folder" &&
        state._currentCaseId === caseId &&
        state.currentFolderId
      ) {
        const updatedTree =
          qc.getQueryData<FolderTreeNode[]>(["evidence-folder-tree", caseId]) ??
          []
        const byId = new Map(
          flattenFolders(updatedTree).map((folder) => [folder.id, folder])
        )
        const ancestors = new Set<string>()
        let current: string | null = state.currentFolderId
        while (current && !ancestors.has(current)) {
          ancestors.add(current)
          current = byId.get(current)?.parent_id ?? null
        }
        useEvidenceStore.setState({
          expandedFolderIds: new Set([
            ...state.expandedFolderIds,
            ...ancestors,
          ]),
        })
      }
    },
    onError: (error) => toast.error(`Could not move: ${error.message}`),
    onSettled: () => {
      inFlight.current = false
    },
  })
  const canMove = Boolean(
    canUploadEvidence && tree.isSuccess && !mutation.isPending
  )
  const invalidReason = (source: MoveSource, target: string | null) =>
    invalidMoveReason(source, target, folders)
  const move = (source: MoveSource, target: string | null) => {
    if (!canMove || inFlight.current) return
    const reason = invalidReason(source, target)
    if (reason) {
      toast.error(reason)
      return
    }
    inFlight.current = true
    mutation.mutate({ source, target })
  }
  const targets = [
    { id: null, name: "Evidence root", depth: -1, path: "Evidence root" },
    ...folders,
  ]
  return (
    <EvidenceMovesContext.Provider
      value={{
        canMove,
        dragging,
        invalidReason,
        move,
        openMove: (source) => {
          if (canMove) {
            mutation.reset()
            setDestination(undefined)
            setRequest(source)
          }
        },
        startDrag: (event, source) => {
          if (!canMove) {
            event.preventDefault()
            return
          }
          event.stopPropagation()
          event.dataTransfer.setData(EVIDENCE_DRAG_TYPE, caseId)
          event.dataTransfer.effectAllowed = "move"
          setDragging(source)
        },
        endDrag: () => setDragging(null),
      }}
    >
      {children}
      <Dialog
        open={request !== null}
        onOpenChange={(open) => {
          if (!open && !mutation.isPending) setRequest(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Move to…</DialogTitle>
            <DialogDescription>
              Choose a destination for{" "}
              {request?.kind === "folder"
                ? `“${request.name}”`
                : `${request?.files.length ?? 0} selected file${request?.files.length === 1 ? "" : "s"}`}
              .
            </DialogDescription>
          </DialogHeader>
          <div
            className="max-h-[45vh] space-y-1 overflow-auto rounded-md border border-border p-2"
            aria-label="Destination folders"
          >
            {targets.map((target) => {
              const reason = request ? invalidReason(request, target.id) : null
              return (
                <button
                  key={target.id ?? "root"}
                  type="button"
                  aria-pressed={destination === target.id}
                  disabled={Boolean(reason) || mutation.isPending}
                  title={reason ?? target.path}
                  onClick={() => setDestination(target.id)}
                  style={{
                    paddingLeft: Math.min(target.depth + 1, 12) * 16 + 8,
                  }}
                  className="flex w-full items-center gap-2 rounded py-2 pr-2 text-left text-sm hover:bg-muted aria-pressed:bg-primary/10 aria-pressed:text-primary disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {target.id ? (
                    <Folder className="size-4 shrink-0" />
                  ) : (
                    <Home className="size-4 shrink-0" />
                  )}
                  <span className="min-w-0 break-words">{target.name}</span>
                  {reason && <span className="ml-auto text-xs">{reason}</span>}
                </button>
              )
            })}
          </div>
          {mutation.isError && (
            <p role="alert" className="text-sm text-destructive">
              {mutation.error.message}
            </p>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              disabled={mutation.isPending}
              onClick={() => setRequest(null)}
            >
              Cancel
            </Button>
            <Button
              disabled={
                !canMove ||
                destination === undefined ||
                !request ||
                Boolean(
                  request &&
                  destination !== undefined &&
                  invalidReason(request, destination)
                )
              }
              onClick={() => {
                if (request && destination !== undefined)
                  move(request, destination)
              }}
            >
              {mutation.isPending ? "Moving…" : "Move here"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </EvidenceMovesContext.Provider>
  )
}
