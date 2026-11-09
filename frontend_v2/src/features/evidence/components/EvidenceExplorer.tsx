import { announce } from "@/features/guidance/announce"
import { OPEN_DELETED_ITEMS } from "@/features/guidance/next-steps"
import { EvidenceMoveProvider } from "./EvidenceMoveProvider"
import { useEffect, useState } from "react"
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom"
import { foldersAPI } from "../folders.api"
import { useQueryClient } from "@tanstack/react-query"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import { TooltipProvider } from "@/components/ui/tooltip"
import { useEvidenceStore } from "../evidence.store"
import { useCreateFolder } from "../hooks/use-folder-mutations"
import { useDeleteFolder } from "../hooks/use-folder-mutations"
import { useDeleteEvidence } from "../hooks/use-evidence-detail"
import { FolderTreeSidebar } from "./FolderTreeSidebar"
import { FileListPanel } from "./FileListPanel"
import { CreateFolderDialog } from "./CreateFolderDialog"
import { DeleteFolderDialog } from "./DeleteFolderDialog"
import { folderDeleteRefusal } from "../folder-delete"
import { DeleteEvidenceDialog } from "./DeleteEvidenceDialog"
import { DeletedEvidenceDialog } from "./DeletedEvidenceDialog"
import { useDeletedItemsEnabled } from "@/features/cases/hooks/use-deleted-items"
import { FolderContextDialog } from "./FolderContextDialog"
import { CaseProcessingProfileDialog } from "./CaseProcessingProfileDialog"
import { toast } from "sonner"
import type { EvidenceFile } from "@/types/evidence.types"

export function EvidenceExplorer() {
  const { id: caseId } = useParams()
  const [searchParams] = useSearchParams()
  const location = useLocation()
  const queryClient = useQueryClient()
  const {
    currentFolderId,
    selectedFileIds,
    clearSelection,
  } = useEvidenceStore()
  const resetForCase = useEvidenceStore((s) => s.resetForCase)
  const openDetail = useEvidenceStore((s) => s.openDetail)
  const revealFile = useEvidenceStore((s) => s.revealFile)

  useEffect(() => {
    if (caseId) resetForCase(caseId)
  }, [caseId, resetForCase])

  useEffect(() => {
    // The attention feed's phone reading items open the processing panel, where the readiness card is.
    if (caseId && searchParams.get("panel") === "processing") useEvidenceStore.getState().openSidebarTo("processing")
  }, [caseId, searchParams])

  useEffect(() => {
    const fileId = searchParams.get("file")
    if (!caseId || !fileId) return
    if (searchParams.get("reveal") === "1") {
      const controller = new AbortController()
      const toastId = toast.loading("Opening file location…")
      const locate = async () => {
        // A sort can change while the lookup is in flight. Resolve its page again
        // before revealing, so the response always matches the rendered order.
        while (!controller.signal.aborted) {
          const { sortBy, sortDirection } = useEvidenceStore.getState()
          const target = await foldersAPI.getFileLocation(caseId, fileId, controller.signal, { sort_by: sortBy, sort_direction: sortDirection })
          const current = useEvidenceStore.getState()
          if (current.sortBy === sortBy && current.sortDirection === sortDirection) return target
        }
        throw new DOMException("Aborted", "AbortError")
      }
      void locate().then(
        (target) => {
          if (controller.signal.aborted) return
          toast.dismiss(toastId)
          void queryClient.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId, target.folder_id] })
          void queryClient.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
          revealFile(target)
        },
        () => {
          if (controller.signal.aborted) return
          toast.dismiss(toastId)
          toast.error("Could not open file location. The file may have been removed or you may no longer have access.")
        },
      )
      return () => {
        controller.abort()
        toast.dismiss(toastId)
      }
    }
    const finiteNumber = (name: string) => {
      const raw = searchParams.get(name)
      if (raw === null) return undefined
      const value = Number(raw)
      return Number.isFinite(value) ? value : undefined
    }
    const page = finiteNumber("page")
    openDetail(fileId, {
      page: page === undefined ? undefined : Math.max(1, Math.floor(page)),
      startSeconds: finiteNumber("start_seconds"),
      endSeconds: finiteNumber("end_seconds"),
      startChar: finiteNumber("start_char"),
    })
  }, [caseId, openDetail, revealFile, searchParams, location.key, queryClient])

  // Dialog state
  const [createFolderOpen, setCreateFolderOpen] = useState(false)
  const [createFolderParentId, setCreateFolderParentId] = useState<string | null>(null)
  const [deleteFolderOpen, setDeleteFolderOpen] = useState(false)
  const [deleteFolderTarget, setDeleteFolderTarget] = useState<{
    id: string
    name: string
  } | null>(null)
  const [deleteFolderError, setDeleteFolderError] = useState<string | null>(null)
  const [folderProfileFolderId, setFolderProfileFolderId] = useState<string | null>(null)
  const [caseProfileOpen, setCaseProfileOpen] = useState(false)
  const [deleteEvidenceOpen, setDeleteEvidenceOpen] = useState(false)
  const [deletedItemsOpen, setDeletedItemsOpen] = useState(false)
  // "Undo from Deleted items" in the next steps after a delete opens the list here (lx-guide B)
  useEffect(() => {
    const show = () => setDeletedItemsOpen(true)
    window.addEventListener(OPEN_DELETED_ITEMS, show)
    return () => window.removeEventListener(OPEN_DELETED_ITEMS, show)
  }, [])
  // Deleted items switched on (server setting, off by default); off, deletes are immediate as before.
  const deletedItems = useDeletedItemsEnabled()
  const [deleteEvidenceTarget, setDeleteEvidenceTarget] = useState<EvidenceFile | null>(null)

  // Mutations
  const createFolderMutation = useCreateFolder(caseId!)
  const deleteFolderMutation = useDeleteFolder(caseId!)
  const deleteEvidenceMutation = useDeleteEvidence(caseId!)

  // Handlers passed down through context
  const handleCreateFolder = (name: string) => {
    createFolderMutation.mutate(
      { name, parentId: createFolderParentId },
      {
        onSuccess: () => {
          setCreateFolderOpen(false)
          toast.success(`Folder "${name}" created`)
        },
        onError: (err) => toast.error(err.message),
      }
    )
  }

  const handleOpenCreateFolder = (parentId: string | null) => {
    setCreateFolderParentId(parentId)
    setCreateFolderOpen(true)
  }

  // The tree's file count is a folder's direct files only; the dialog asks the server for everything the delete removes.
  const handleOpenDeleteFolder = (id: string, name: string) => {
    setDeleteFolderTarget({ id, name })
    setDeleteFolderError(null)
    setDeleteFolderOpen(true)
  }

  const handleConfirmDeleteFolder = () => {
    if (!deleteFolderTarget) return
    deleteFolderMutation.mutate(deleteFolderTarget.id, {
      onSuccess: () => {
        setDeleteFolderOpen(false)
        setDeleteFolderTarget(null)
        if (deletedItems) announce(caseId, { kind: "deleted", count: 1, noun: "folder", where: "evidence" })
        toast.success(
          deletedItems
            ? `Folder "${deleteFolderTarget.name}" moved to Deleted items, with its files, for 30 days`
            : `Folder "${deleteFolderTarget.name}" deleted`
        )
      },
      onError: (err) => {
        const message = folderDeleteRefusal(err)
        setDeleteFolderError(message)
        toast.error(message)
      },
    })
  }

  const handleOpenDeleteEvidence = (file?: EvidenceFile) => {
    setDeleteEvidenceTarget(file ?? null)
    setDeleteEvidenceOpen(true)
  }

  const handleConfirmDeleteEvidence = (deleteExclusiveEntities: boolean) => {
    const ids = deleteEvidenceTarget
      ? [deleteEvidenceTarget.id]
      : Array.from(selectedFileIds)

    const deleteNext = (index: number) => {
      if (index >= ids.length) {
        if (deletedItems) announce(caseId, { kind: "deleted", count: ids.length, noun: "file", where: "evidence" })
        toast.success(
          deletedItems
            ? `Moved ${ids.length} file${ids.length !== 1 ? "s" : ""} to Deleted items (restorable for 30 days)`
            : `Deleted ${ids.length} file${ids.length !== 1 ? "s" : ""}`
        )
        setDeleteEvidenceOpen(false)
        setDeleteEvidenceTarget(null)
        clearSelection()
        return
      }
      deleteEvidenceMutation.mutate(
        { evidenceId: ids[index], deleteExclusiveEntities },
        {
          onSuccess: () => deleteNext(index + 1),
          // A refused file stops the run; the files before it are deleted and
          // the rest are untouched, so say both rather than failing silently.
          onError: (err) => {
            const done = index
              ? `Deleted ${index} of ${ids.length} files. `
              : ""
            const left = ids.length - index - 1
            const rest =
              left === 1
                ? " The other selected file was not deleted."
                : left > 1
                  ? ` The other ${left} selected files were not deleted.`
                  : ""
            toast.error(`${done}${err.message}${rest}`)
            setDeleteEvidenceOpen(false)
            setDeleteEvidenceTarget(null)
            if (index) clearSelection()
          },
        }
      )
    }
    deleteNext(0)
  }

  return (
    <EvidenceMoveProvider key={caseId} caseId={caseId!}>
    <TooltipProvider delayDuration={300}>
      <div className="flex h-full flex-col overflow-hidden bg-background">
        {searchParams.get("from") === "financial" && (
          <div className="border-b p-3 text-sm">
            <Link className="underline" to={`/cases/${caseId}/financial?view=statements&files=1`}>
              Back to Financial sources
            </Link>
            <span className="ml-3 text-muted-foreground">Review this source and its processing status. Your Financial selection is saved.</span>
          </div>
        )}
        <ResizablePanelGroup orientation="horizontal" className="flex-1">
          {/* Left sidebar: Folder tree */}
          <ResizablePanel
            defaultSize="20"
            minSize="15"
            maxSize="35"
            collapsible
            collapsedSize="0"
          >
            <FolderTreeSidebar
              caseId={caseId!}
              onCreateFolder={handleOpenCreateFolder}
              onDeleteFolder={handleOpenDeleteFolder}
              onEditFolderProfile={setFolderProfileFolderId}
              onEditCaseProfile={() => setCaseProfileOpen(true)}
              onOpenDeleted={deletedItems ? () => setDeletedItemsOpen(true) : undefined}
            />
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Center: File list */}
          <ResizablePanel defaultSize="80" minSize="30">
            <FileListPanel
              caseId={caseId!}
              onCreateFolder={() => handleOpenCreateFolder(currentFolderId)}
              onDeleteFiles={() => handleOpenDeleteEvidence()}
              onDeleteFile={(file) => handleOpenDeleteEvidence(file)}
            />
          </ResizablePanel>
        </ResizablePanelGroup>

        {/* Dialog portals */}
        {deletedItems && (
          <DeletedEvidenceDialog caseId={caseId!} open={deletedItemsOpen} onOpenChange={setDeletedItemsOpen} />
        )}
        <CreateFolderDialog
          open={createFolderOpen}
          onOpenChange={setCreateFolderOpen}
          onConfirm={handleCreateFolder}
          isPending={createFolderMutation.isPending}
        />

        <DeleteFolderDialog
          open={deleteFolderOpen}
          onOpenChange={setDeleteFolderOpen}
          caseId={caseId!}
          folderId={deleteFolderTarget?.id ?? null}
          folderName={deleteFolderTarget?.name ?? ""}
          onConfirm={handleConfirmDeleteFolder}
          isPending={deleteFolderMutation.isPending}
          error={deleteFolderError}
          deletedItems={deletedItems}
        />

        <DeleteEvidenceDialog
          open={deleteEvidenceOpen}
          onOpenChange={setDeleteEvidenceOpen}
          fileCount={deleteEvidenceTarget ? 1 : selectedFileIds.size}
          onConfirm={handleConfirmDeleteEvidence}
          isPending={deleteEvidenceMutation.isPending}
          deletedItems={deletedItems}
        />

        {folderProfileFolderId ? (
          <FolderContextDialog
            folderId={folderProfileFolderId}
            caseId={caseId!}
            open={!!folderProfileFolderId}
            onOpenChange={(nextOpen) => {
              if (!nextOpen) {
                setFolderProfileFolderId(null)
              }
            }}
          />
        ) : null}

        <CaseProcessingProfileDialog
          caseId={caseId!}
          open={caseProfileOpen}
          onOpenChange={setCaseProfileOpen}
        />
      </div>
    </TooltipProvider>
    </EvidenceMoveProvider>
  )
}
