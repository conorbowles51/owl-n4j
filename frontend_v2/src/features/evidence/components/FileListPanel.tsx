import { useRef, useState, useCallback } from "react"
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Checkbox } from "@/components/ui/checkbox"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { Upload } from "lucide-react"
import { useFolderContents } from "../hooks/use-folder-contents"
import { useEvidenceStore } from "../evidence.store"
import { getFileTypeCategory } from "../utils/file-types"
import { FolderBreadcrumbs } from "./FolderBreadcrumbs"
import { FileListToolbar } from "./FileListToolbar"
import { FileRow } from "./FileRow"
import { FolderRow } from "./FolderRow"
import { InlineDropZone } from "./InlineDropZone"
import type { EvidenceFile } from "@/types/evidence.types"

interface FileListPanelProps {
  caseId: string
  onCreateFolder: () => void
  onDeleteFiles: () => void
  onDeleteFile: (file: EvidenceFile) => void
}

export function FileListPanel({
  caseId,
  onCreateFolder,
  onDeleteFiles,
  onDeleteFile,
}: FileListPanelProps) {
  const {
    currentFolderId,
    setCurrentFolder,
    selectedFileIds,
    toggleFileSelection,
    selectAllFiles,
    clearSelection,
    searchTerm,
    statusFilter,
    typeFilter,
  } = useEvidenceStore()

  const { data: contents, isLoading } = useFolderContents(caseId, currentFolderId)
  const containerRef = useRef<HTMLDivElement>(null)
  const [isDraggingExternal, setIsDraggingExternal] = useState(false)

  // Filter files based on search/filters
  const filteredFiles = contents?.files?.filter((f) => {
    if (
      searchTerm &&
      !f.original_filename.toLowerCase().includes(searchTerm.toLowerCase())
    ) {
      return false
    }
    if (statusFilter !== "all" && f.status !== statusFilter) return false
    if (typeFilter && getFileTypeCategory(f.original_filename) !== typeFilter) return false
    return true
  })

  // Filter folders based on search
  const filteredFolders = contents?.folders?.filter((f) => {
    if (searchTerm && !f.name.toLowerCase().includes(searchTerm.toLowerCase())) {
      return false
    }
    return true
  })

  const allFileIds = filteredFiles?.map((f) => f.id) ?? []
  const allSelected = allFileIds.length > 0 && selectedFileIds.size === allFileIds.length
  const someSelected = selectedFileIds.size > 0 && !allSelected

  const handleToggleAll = () => {
    if (allSelected) {
      clearSelection()
    } else {
      selectAllFiles(allFileIds)
    }
  }

  const handleFolderNavigate = (folderId: string) => {
    setCurrentFolder(folderId)
    clearSelection()
  }

  // Track drag state for external file drops
  const dragCounterRef = useRef(0)

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    if (e.dataTransfer.types.includes("Files")) {
      dragCounterRef.current++
      setIsDraggingExternal(true)
    }
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    dragCounterRef.current--
    if (dragCounterRef.current === 0) {
      setIsDraggingExternal(false)
    }
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
  }, [])

  const handleDrop = useCallback(() => {
    dragCounterRef.current = 0
    setIsDraggingExternal(false)
  }, [])

  const hasContent =
    (filteredFolders && filteredFolders.length > 0) ||
    (filteredFiles && filteredFiles.length > 0)

  return (
    <div
      ref={containerRef}
      className="flex h-full flex-col overflow-hidden"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* Breadcrumbs */}
      <div className="border-b border-border px-4 py-2">
        <FolderBreadcrumbs
          breadcrumbs={contents?.breadcrumbs ?? []}
          currentFolder={contents?.folder ?? null}
          onNavigate={(id) => {
            setCurrentFolder(id)
            clearSelection()
          }}
        />
      </div>

      {/* Toolbar */}
      <FileListToolbar
        caseId={caseId}
        onCreateFolder={onCreateFolder}
        onDeleteFiles={onDeleteFiles}
      />

      {/* Inline drop zone overlay */}
      {isDraggingExternal && (
        <InlineDropZone
          caseId={caseId}
          folderId={currentFolderId}
          folderName={contents?.folder?.name ?? "Root"}
          onDropComplete={() => setIsDraggingExternal(false)}
        />
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : !hasContent ? (
          <EmptyState
            icon={Upload}
            title="No files yet"
            description="Drag and drop files here or use the upload button."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <Checkbox
                    checked={allSelected}
                    indeterminate={someSelected}
                    onCheckedChange={handleToggleAll}
                  />
                </TableHead>
                <TableHead>Name</TableHead>
                <TableHead className="w-20">Type</TableHead>
                <TableHead className="w-20">Size</TableHead>
                <TableHead className="w-28">Status</TableHead>
                <TableHead className="w-20">Entities</TableHead>
                <TableHead className="w-28">Date</TableHead>
                <TableHead className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredFolders?.map((folder) => (
                <FolderRow
                  key={folder.id}
                  folder={folder}
                  onNavigate={handleFolderNavigate}
                />
              ))}
              {filteredFiles?.map((file) => (
                <FileRow
                  key={file.id}
                  file={file}
                  caseId={caseId}
                  onDelete={onDeleteFile}
                />
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  )
}
