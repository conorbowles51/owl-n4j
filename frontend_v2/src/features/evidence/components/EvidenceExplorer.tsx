import { useEffect, useState } from "react"
import { useParams } from "react-router-dom"
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
  const {
    currentFolderId,
    selectedFileIds,
    clearSelection,
  } = useEvidenceStore()
  const resetForCase = useEvidenceStore((s) => s.resetForCase)

  useEffect(() => {
    if (caseId) resetForCase(caseId)
  }, [caseId, resetForCase])

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
    <TooltipProvider delayDuration={300}>
      <div className="flex h-full flex-col overflow-hidden">
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
  )
}
