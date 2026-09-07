import { EvidenceMoveProvider } from "./EvidenceMoveProvider"
import { useEffect, useState } from "react"
import { useLocation, useParams, useSearchParams } from "react-router-dom"
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
import { DeleteEvidenceDialog } from "./DeleteEvidenceDialog"
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
    fileCount: number
  } | null>(null)
  const [folderProfileFolderId, setFolderProfileFolderId] = useState<string | null>(null)
  const [caseProfileOpen, setCaseProfileOpen] = useState(false)
  const [deleteEvidenceOpen, setDeleteEvidenceOpen] = useState(false)
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

  const handleOpenDeleteFolder = (id: string, name: string, fileCount: number) => {
    setDeleteFolderTarget({ id, name, fileCount })
    setDeleteFolderOpen(true)
  }

  const handleConfirmDeleteFolder = () => {
    if (!deleteFolderTarget) return
    deleteFolderMutation.mutate(deleteFolderTarget.id, {
      onSuccess: () => {
        setDeleteFolderOpen(false)
        setDeleteFolderTarget(null)
        toast.success(`Folder "${deleteFolderTarget.name}" deleted`)
      },
      onError: (err) => toast.error(err.message),
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
        toast.success(`Deleted ${ids.length} file${ids.length !== 1 ? "s" : ""}`)
        setDeleteEvidenceOpen(false)
        setDeleteEvidenceTarget(null)
        clearSelection()
        return
      }
      deleteEvidenceMutation.mutate(
        { evidenceId: ids[index], deleteExclusiveEntities },
        { onSuccess: () => deleteNext(index + 1) }
      )
    }
    deleteNext(0)
  }

  return (
    <EvidenceMoveProvider key={caseId} caseId={caseId!}>
    <TooltipProvider delayDuration={300}>
      <div className="flex h-full flex-col overflow-hidden bg-background">
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
        <CreateFolderDialog
          open={createFolderOpen}
          onOpenChange={setCreateFolderOpen}
          onConfirm={handleCreateFolder}
          isPending={createFolderMutation.isPending}
        />

        <DeleteFolderDialog
          open={deleteFolderOpen}
          onOpenChange={setDeleteFolderOpen}
          folderName={deleteFolderTarget?.name ?? ""}
          fileCount={deleteFolderTarget?.fileCount ?? 0}
          onConfirm={handleConfirmDeleteFolder}
          isPending={deleteFolderMutation.isPending}
        />

        <DeleteEvidenceDialog
          open={deleteEvidenceOpen}
          onOpenChange={setDeleteEvidenceOpen}
          fileCount={deleteEvidenceTarget ? 1 : selectedFileIds.size}
          onConfirm={handleConfirmDeleteEvidence}
          isPending={deleteEvidenceMutation.isPending}
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
