import {
  useEvidenceMoves,
  EVIDENCE_DRAG_TYPE,
} from "../hooks/use-evidence-moves"
import { useRef, useState, useCallback, useEffect } from "react"
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
import {
  Upload,
  Play,
  ChevronLeft,
  ChevronRight,
  ContactRound,
  Pin,
} from "lucide-react"
import { EvidenceSortHeader } from "./EvidenceTableHeaders"
import {
  useFolderContents,
  useFilenameSearch,
} from "../hooks/use-folder-contents"
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
import { AddEvidenceToDossierDialog } from "@/features/dossiers/components/AddEvidenceToDossierDialog"
import { useCase } from "@/features/cases/hooks/use-cases"
import { useCasePermissions } from "@/features/cases/hooks/use-case-permissions"
import {
  useBulkPinItems,
  usePinItem,
  usePinStatus,
  useUnpinItem,
} from "@/features/workspace/hooks/use-workspace"

import { FILE_PAGE_SIZE } from "../folders.api"

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
  const moves = useEvidenceMoves()
  const {
    searchMode,
    sortBy,
    sortDirection,
    nameWidth,
    filePage,
    setFilePage,
    revealTargetFileId,
    finishReveal,
    currentFolderId,
    setCurrentFolder,
    selectedFileIds,
    selectAllFiles,
    clearSelection,
    fileSearchTerm,
    statusFilter,
    typeFilter,
  } = useEvidenceStore()

  const [debouncedSearch, setDebouncedSearch] = useState(fileSearchTerm)
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(fileSearchTerm), 250)
    return () => clearTimeout(timer)
  }, [fileSearchTerm])
  const searching = searchMode !== "text" && fileSearchTerm.length > 0
  const searchSettled = debouncedSearch === fileSearchTerm
  const params = {
    limit: FILE_PAGE_SIZE,
    offset: filePage * FILE_PAGE_SIZE,
    status: statusFilter !== "all" ? statusFilter : undefined,
    type: typeFilter || undefined,
    sort_by: sortBy,
    sort_direction: sortDirection,
  }
  const browse = useFolderContents(caseId, currentFolderId, params)
  const search = useFilenameSearch(
    caseId,
    fileSearchTerm,
    searchMode === "subtree" ? "subtree" : "case",
    currentFolderId,
    params,
    searching && searchSettled
  )
  const activeQuery = searching ? search : browse
  const contents = browse.data
  const browseFolderName = currentFolderId ? contents?.folder?.name ?? "Selected folder" : "Evidence root"
  const isLoading = activeQuery.isLoading || (searching && !searchSettled)
  const { isFetching, isError } = activeQuery
  const containerRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!revealTargetFileId || isLoading || isFetching) return
    const row = Array.from(
      containerRef.current?.querySelectorAll<HTMLElement>(
        "[data-evidence-file-id]"
      ) ?? []
    ).find((element) => element.dataset.evidenceFileId === revealTargetFileId)
    if (row) {
      row.scrollIntoView({ block: "center" })
      row.focus({ preventScroll: true })
    } else {
      toast.error(
        isError
          ? "Could not load the file's folder. Please try again."
          : "The file's location changed. Please open its location again."
      )
    }
    finishReveal()
  }, [
    contents,
    isLoading,
    isFetching,
    isError,
    revealTargetFileId,
    finishReveal,
  ])
  const [isDraggingExternal, setIsDraggingExternal] = useState(false)
  const [dossierFiles, setDossierFiles] = useState<
    Array<{ id: string; name: string }>
  >([])
  const caseQuery = useCase(caseId)
  const { canEdit } = useCasePermissions(caseQuery.data)

  const queryClient = useQueryClient()
  const processMutation = useMutation({
    mutationFn: (data: { fileIds: string[] }) =>
      evidenceAPI.processBackground(caseId, data.fileIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["evidence-jobs", caseId] })
      queryClient.invalidateQueries({
        queryKey: ["evidence-folder-contents", caseId],
      })
      queryClient.invalidateQueries({
        queryKey: ["evidence-folder-tree", caseId],
      })
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

  const filteredFiles = activeQuery.data?.files ?? []
  const filteredFolders = searching ? [] : (contents?.folders ?? [])
  const visibleFileIds = filteredFiles.map((file) => file.id)
  const pinStatusQuery = usePinStatus(caseId, visibleFileIds)
  const pinMutation = usePinItem(caseId)
  const bulkPinMutation = useBulkPinItems(caseId)
  const unpinMutation = useUnpinItem(caseId)
  const pinStatus = pinStatusQuery.data ?? {}
  const fileTotal = activeQuery.data?.file_total ?? 0
  const pageCount = Math.max(1, Math.ceil(fileTotal / FILE_PAGE_SIZE))
  const canPageBack = filePage > 0
  const canPageForward = filePage < pageCount - 1
  const pageStart = fileTotal === 0 ? 0 : filePage * FILE_PAGE_SIZE + 1
  const pageEnd = Math.min((filePage + 1) * FILE_PAGE_SIZE, fileTotal)

  useEffect(() => {
    if (
      activeQuery.isSuccess &&
      !isFetching &&
      !isLoading &&
      filePage >= pageCount
    )
      setFilePage(pageCount - 1)
  }, [
    activeQuery.isSuccess,
    isFetching,
    isLoading,
    filePage,
    pageCount,
    setFilePage,
  ])

  const allFileIds = filteredFiles?.map((f) => f.id) ?? []
  const allSelected =
    allFileIds.length > 0 && selectedFileIds.size === allFileIds.length
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
    if (
      e.dataTransfer.types.includes("Files") &&
      !e.dataTransfer.types.includes(EVIDENCE_DRAG_TYPE)
    ) {
      dragCounterRef.current++
      setIsDraggingExternal(true)
    }
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes("Files")) return
    e.preventDefault()
    dragCounterRef.current = Math.max(0, dragCounterRef.current - 1)
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
          folderName={browseFolderName}
          onDropComplete={handleDrop}
        />
      )}

      <div className="flex flex-wrap items-center justify-between gap-1 border-b border-border px-4 py-1.5 text-xs text-muted-foreground">
        <span>
          {searching
            ? `${fileTotal.toLocaleString()} filename match${fileTotal === 1 ? "" : "es"}${searchMode === "subtree" ? " in this folder and subfolders" : " in this case"}`
            : `${fileTotal.toLocaleString()} files`}
          {isFetching && !isLoading ? " · Updating…" : ""}
        </span>
        <span
          className="min-w-0 truncate"
          title={browseFolderName}
        >
          Upload destination: {browseFolderName}
        </span>
      </div>
      {/* Content */}
      <div className="flex-1 overflow-auto">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : isError ? (
          <div role="alert" className="p-8 text-center text-sm">
            <p>
              Could not load {searching ? "search results" : "this folder"}.{" "}
              {activeQuery.error?.message}
            </p>
            <Button
              className="mt-3"
              variant="outline"
              onClick={() => void activeQuery.refetch()}
            >
              Try again
            </Button>
          </div>
        ) : !hasContent ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
            <Upload className="size-10 text-muted-foreground/30" />
            <p className="text-sm font-medium text-muted-foreground">
              {searching
                ? "No matching filenames"
                : statusFilter !== "all" || typeFilter
                  ? "No files match these filters"
                  : "No files yet"}
            </p>
            <p className="text-xs text-muted-foreground/70">
              {searching
                ? "Try a different filename or search scope."
                : statusFilter !== "all" || typeFilter
                  ? "Change the status or type filter to see more files."
                  : "Drop files here or click Upload to get started"}
            </p>
          </div>
        ) : (
          <Table
            className="table-fixed"
            style={{
              width: nameWidth === null ? "100%" : nameWidth + 624,
              minWidth: nameWidth === null ? 804 : nameWidth + 624,
            }}
          >
            <colgroup>
              <col style={{ width: 32 }} />
              <col
                style={nameWidth === null ? undefined : { width: nameWidth }}
              />
              <col style={{ width: 80 }} />
              <col style={{ width: 80 }} />
              <col style={{ width: 112 }} />
              <col style={{ width: 80 }} />
              <col style={{ width: 128 }} />
              <col style={{ width: 112 }} />
            </colgroup>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <Checkbox
                    aria-label="Select all files on this page"
                    checked={
                      allSelected
                        ? true
                        : someSelected
                          ? "indeterminate"
                          : false
                    }
                    onCheckedChange={handleToggleAll}
                  />
                </TableHead>
                <EvidenceSortHeader column="name">Name</EvidenceSortHeader>
                <TableHead className="w-20">Type</TableHead>
                <TableHead className="w-20">Size</TableHead>
                <TableHead className="w-28">Status</TableHead>
                <TableHead className="w-20">Entities</TableHead>
                <EvidenceSortHeader column="date">
                  Date added
                </EvidenceSortHeader>
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
                  dragSource={{
                    kind: "files",
                    files: selectedFileIds.has(file.id)
                      ? filteredFiles.filter((entry) =>
                          selectedFileIds.has(entry.id)
                        )
                      : [file],
                  }}
                  caseId={caseId}
                  onDelete={onDeleteFile}
                  onAddToDossier={
                    canEdit
                      ? (file) =>
                          setDossierFiles([
                            { id: file.id, name: file.original_filename },
                          ])
                      : undefined
                  }
                  isPinned={Boolean(pinStatus[file.id])}
                  pinId={pinStatus[file.id]}
                  onPin={
                    canEdit
                      ? (fileId) =>
                          pinMutation.mutate(
                            { itemType: "evidence", itemId: fileId },
                            {
                              onSuccess: () =>
                                toast.success("Pinned to workspace"),
                            }
                          )
                      : undefined
                  }
                  onUnpin={
                    canEdit
                      ? (pinId) =>
                          unpinMutation.mutate(pinId, {
                            onSuccess: () =>
                              toast.success("Removed from workspace"),
                          })
                      : undefined
                  }
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
              aria-label="Previous file page"
              disabled={!canPageBack}
              onClick={() => {
                setFilePage(filePage - 1)
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
              aria-label="Next file page"
              disabled={!canPageForward}
              onClick={() => {
                setFilePage(Math.min(pageCount - 1, filePage + 1))
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
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex w-max max-w-[calc(100%-2rem)] flex-wrap justify-center items-center gap-3 rounded-lg border border-border bg-card px-4 py-2 shadow-lg">
          <span className="text-xs font-medium text-muted-foreground">
            {selectedFileIds.size} file{selectedFileIds.size !== 1 ? "s" : ""}{" "}
            selected
          </span>
          {moves?.canMove && (
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                moves.openMove({
                  kind: "files",
                  files: filteredFiles.filter((file) =>
                    selectedFileIds.has(file.id)
                  ),
                })
              }
            >
              Move to…
            </Button>
          )}
          <Button size="sm" onClick={handleProcessSelected}>
            <Play className="mr-1.5 size-3.5" />
            Process
          </Button>
          {canEdit ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                bulkPinMutation.mutate(Array.from(selectedFileIds), {
                  onSuccess: (result) => {
                    toast.success(
                      result.created > 0
                        ? `${result.created} item${result.created === 1 ? "" : "s"} pinned to workspace`
                        : "All selected evidence is already pinned"
                    )
                  },
                })
              }
              disabled={bulkPinMutation.isPending}
            >
              <Pin className="mr-1.5 size-3.5" /> Pin to workspace
            </Button>
          ) : null}
          {canEdit ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                setDossierFiles(
                  filteredFiles
                    .filter((file) => selectedFileIds.has(file.id))
                    .map((file) => ({
                      id: file.id,
                      name: file.original_filename,
                    }))
                )
              }
            >
              <ContactRound className="mr-1.5 size-3.5" /> Add to Dossier
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" onClick={clearSelection}>
            Clear
          </Button>
        </div>
      )}
      <AddEvidenceToDossierDialog
        caseId={caseId}
        files={dossierFiles}
        open={dossierFiles.length > 0}
        onOpenChange={(value) => {
          if (!value) setDossierFiles([])
        }}
        onDone={clearSelection}
      />
    </div>
  )
}
