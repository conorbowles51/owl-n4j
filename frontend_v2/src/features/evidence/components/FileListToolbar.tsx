import { useRef } from "react"
import {
  Search,
  X,
  FolderPlus,
  Upload,
  Play,
  Trash2,
  Activity,
} from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select"
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip"
import { useEvidenceStore } from "../evidence.store"
import { useUploadToFolder } from "../hooks/use-upload-to-folder"
import { useJobs } from "../hooks/use-jobs"
import { evidenceAPI } from "../api"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

interface FileListToolbarProps {
  caseId: string
  onCreateFolder: () => void
  onDeleteFiles: () => void
}

export function FileListToolbar({
  caseId,
  onCreateFolder,
  onDeleteFiles,
}: FileListToolbarProps) {
  const {
    searchTerm,
    setSearchTerm,
    statusFilter,
    setStatusFilter,
    typeFilter,
    setTypeFilter,
    selectedFileIds,
    currentFolderId,
    sidebarOpen,
    sidebarTab,
    openSidebarTo,
    setSidebarOpen,
  } = useEvidenceStore()

  const fileInputRef = useRef<HTMLInputElement>(null)
  const uploadMutation = useUploadToFolder(caseId)
  const { data: jobs } = useJobs(caseId)
  const activeCount = jobs?.filter(
    (j) => !["completed", "failed"].includes(j.status)
  ).length ?? 0
  const queryClient = useQueryClient()
  const processMutation = useMutation({
    mutationFn: (data: { fileIds: string[] }) =>
      evidenceAPI.processBackground(caseId, data.fileIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["evidence-jobs", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
    },
  })

  const selectionCount = selectedFileIds.size

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    uploadMutation.mutate(
      { files: Array.from(files), folderId: currentFolderId },
      {
        onSuccess: () => toast.success(`Uploaded ${files.length} file${files.length !== 1 ? "s" : ""}`),
        onError: (err) => toast.error(err.message),
      }
    )

    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  const handleProcess = () => {
    if (selectionCount === 0) return
    processMutation.mutate(
      { fileIds: Array.from(selectedFileIds) },
      {
        onSuccess: () => {
          toast.success("Processing started")
          useEvidenceStore.getState().clearSelection()
          useEvidenceStore.getState().openSidebarTo("processing")
        },
        onError: (err) => toast.error(err.message),
      }
    )
  }

  return (
    <div className="flex items-center gap-2 border-b border-border px-4 py-2">
      {/* Search */}
      <div className="relative max-w-xs flex-1">
        <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search files..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="h-8 pl-8 pr-7 text-xs"
        />
        {searchTerm && (
          <button
            onClick={() => setSearchTerm("")}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="size-3" />
          </button>
        )}
      </div>

      {/* Status filter */}
      <Select
        value={statusFilter}
        onValueChange={(v) => setStatusFilter(v as typeof statusFilter)}
      >
        <SelectTrigger size="sm" className="h-8 w-[130px] text-xs">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Status</SelectItem>
          <SelectItem value="unprocessed">Unprocessed</SelectItem>
          <SelectItem value="processing">Processing</SelectItem>
          <SelectItem value="processed">Processed</SelectItem>
          <SelectItem value="failed">Failed</SelectItem>
        </SelectContent>
      </Select>

      {/* Type filter */}
      <Select value={typeFilter || "all"} onValueChange={(v) => setTypeFilter(v === "all" ? "" : v)}>
        <SelectTrigger size="sm" className="h-8 w-[120px] text-xs">
          <SelectValue placeholder="Type" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Types</SelectItem>
          <SelectItem value="Document">Document</SelectItem>
          <SelectItem value="Image">Image</SelectItem>
          <SelectItem value="Audio">Audio</SelectItem>
          <SelectItem value="Video">Video</SelectItem>
          <SelectItem value="Data">Data</SelectItem>
        </SelectContent>
      </Select>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Action buttons */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 text-xs"
            onClick={onCreateFolder}
          >
            <FolderPlus className="size-3.5" />
            New Folder
          </Button>
        </TooltipTrigger>
        <TooltipContent>Create a new folder</TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 text-xs"
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload className="size-3.5" />
            Upload
          </Button>
        </TooltipTrigger>
        <TooltipContent>Upload files to this folder</TooltipContent>
      </Tooltip>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="primary"
            size="sm"
            className="h-8 gap-1.5 text-xs"
            disabled={selectionCount === 0 || processMutation.isPending}
            onClick={handleProcess}
          >
            <Play className="size-3.5" />
            Process
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          {selectionCount === 0
            ? "Select files to process"
            : `Process ${selectionCount} selected file${selectionCount !== 1 ? "s" : ""}`}
        </TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 text-xs text-red-600 hover:text-red-600 dark:text-red-400 dark:hover:text-red-400"
            disabled={selectionCount === 0}
            onClick={onDeleteFiles}
          >
            <Trash2 className="size-3.5" />
            Delete
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          {selectionCount === 0
            ? "Select files to delete"
            : `Delete ${selectionCount} selected file${selectionCount !== 1 ? "s" : ""}`}
        </TooltipContent>
      </Tooltip>

      {/* Divider */}
      <div className="h-5 w-px bg-border" />

      {/* Jobs toggle */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant={sidebarOpen && sidebarTab === "processing" ? "secondary" : "outline"}
            size="sm"
            className="h-8 gap-1.5 text-xs"
            onClick={() => {
              if (sidebarOpen && sidebarTab === "processing") {
                setSidebarOpen(false)
              } else {
                openSidebarTo("processing")
              }
            }}
          >
            <Activity className="size-3.5" />
            Jobs
            {activeCount > 0 && (
              <Badge variant="info" className="ml-0.5 px-1 py-0 text-[9px] h-4">
                {activeCount}
              </Badge>
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          {sidebarOpen && sidebarTab === "processing" ? "Hide processing panel" : "Show processing panel"}
        </TooltipContent>
      </Tooltip>
    </div>
  )
}
