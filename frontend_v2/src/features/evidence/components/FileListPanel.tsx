import { useRef, useState, useCallback } from "react"
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Checkbox } from "@/components/ui/checkbox"
import { Button } from "@/components/ui/button"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { Upload, Play, ChevronLeft, ChevronRight } from "lucide-react"
import { useFolderContents } from "../hooks/use-folder-contents"
import { useEvidenceStore } from "../evidence.store"
import { evidenceAPI } from "../api"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { FolderBreadcrumbs } from "./FolderBreadcrumbs"
import { FileListToolbar } from "./FileListToolbar"
import { FileRow } from "./FileRow"
import { FolderRow } from "./FolderRow"
import { InlineDropZone } from "./InlineDropZone"
import type { EvidenceFile } from "@/types/evidence.types"

const FILE_PAGE_SIZE = 250

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
    selectAllFiles,
    clearSelection,
    searchTerm,
    statusFilter,
    typeFilter,
  } = useEvidenceStore()

  const pagingKey = [
    currentFolderId ?? "root",
    searchTerm,
    statusFilter,
    typeFilter,
  ].join("\u001f")
  const [filePaging, setFilePaging] = useState({ key: "", page: 0 })
  const filePage = filePaging.key === pagingKey ? filePaging.page : 0
  const setFilePageForCurrentView = useCallback(
    (nextPage: number | ((page: number) => number)) => {
      setFilePaging((current) => {
        const currentPage = current.key === pagingKey ? current.page : 0
        const resolvedPage =
          typeof nextPage === "function" ? nextPage(currentPage) : nextPage
        return { key: pagingKey, page: Math.max(0, resolvedPage) }
      })
    },
    [pagingKey]
  )
  const { data: contents, isLoading } = useFolderContents(caseId, currentFolderId, {
    limit: FILE_PAGE_SIZE,
    offset: filePage * FILE_PAGE_SIZE,
    search: searchTerm || undefined,
    status: statusFilter !== "all" ? statusFilter : undefined,
    type: typeFilter || undefined,
  })
  const containerRef = useRef<HTMLDivElement>(null)
  const [isDraggingExternal, setIsDraggingExternal] = useState(false)

  const queryClient = useQueryClient()
  const processMutation = useMutation({
    mutationFn: (data: { fileIds: string[] }) =>
      evidenceAPI.processBackground(caseId, data.fileIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["evidence-jobs", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
    },
  })

  const handleProcessSelected = () => {
    if (selectedFileIds.size === 0) return
    processMutation.mutate(
      { fileIds: Array.from(selectedFileIds) },
      {
        onSuccess: () => {
          toast.success("Processing started")
          clearSelection()
        },
        onError: (err) => toast.error(err.message),
      }
    )
  }

  const filteredFiles = contents?.files ?? []
  const filteredFolders = contents?.folders ?? []
  const fileTotal = contents?.file_total ?? 0
  const pageCount = Math.max(1, Math.ceil(fileTotal / FILE_PAGE_SIZE))
  const canPageBack = filePage > 0
  const canPageForward = filePage < pageCount - 1
  const pageStart = fileTotal === 0 ? 0 : filePage * FILE_PAGE_SIZE + 1
  const pageEnd = Math.min((filePage + 1) * FILE_PAGE_SIZE, fileTotal)

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
      className="relative flex h-full flex-col overflow-hidden"
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
          <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
            <Upload className="size-10 text-muted-foreground/30" />
            <p className="text-sm font-medium text-muted-foreground">
              No files yet
            </p>
            <p className="text-xs text-muted-foreground/70">
              Drop files here or click Upload to get started
            </p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <Checkbox
                    checked={allSelected ? true : someSelected ? "indeterminate" : false}
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
              {filteredFolders.map((folder) => (
                <FolderRow
                  key={folder.id}
                  folder={folder}
                  onNavigate={handleFolderNavigate}
                />
              ))}
              {filteredFiles.map((file) => (
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

      {fileTotal > FILE_PAGE_SIZE && (
        <div className="flex items-center justify-between border-t border-border px-4 py-1.5 text-xs text-muted-foreground">
          <span>
            Showing {pageStart}-{pageEnd} of {fileTotal.toLocaleString()} files
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon-sm"
              disabled={!canPageBack}
              onClick={() => {
                setFilePageForCurrentView((page) => Math.max(0, page - 1))
                clearSelection()
              }}
            >
              <ChevronLeft className="size-3.5" />
            </Button>
            <span className="mx-2 tabular-nums">
              {filePage + 1} / {pageCount}
            </span>
            <Button
              variant="ghost"
              size="icon-sm"
              disabled={!canPageForward}
              onClick={() => {
                setFilePageForCurrentView((page) => Math.min(pageCount - 1, page + 1))
                clearSelection()
              }}
            >
              <ChevronRight className="size-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* Floating selection action bar */}
      {selectedFileIds.size > 0 && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-2 shadow-lg">
          <span className="text-xs font-medium text-muted-foreground">
            {selectedFileIds.size} file{selectedFileIds.size !== 1 ? "s" : ""} selected
          </span>
          <Button size="sm" onClick={handleProcessSelected}>
            <Play className="mr-1.5 size-3.5" />
            Process
          </Button>
          <Button size="sm" variant="ghost" onClick={clearSelection}>
            Clear
          </Button>
        </div>
      )}
    </div>
  )
}
