import {
  useRef,
  useState,
  type ChangeEvent,
  type InputHTMLAttributes,
} from "react"
import {
  Search,
  X,
  FolderPlus,
  Upload,
  FolderUp,
  Smartphone,
  FileArchive,
  ChevronDown,
  Play,
  Trash2,
} from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip"
import { useEvidenceStore } from "../evidence.store"
import { useUploadToFolder } from "../hooks/use-upload-to-folder"
import { useGuardedProcess } from "../hooks/use-guarded-process"
import { ProcessHoldDialog } from "./ProcessHoldDialog"
import { toast } from "sonner"
import { EvidenceFinancialPicker } from "@/features/financial/components/EvidenceFinancialPicker"
import { FinancialAccessProvider } from "@/features/financial/components/FinancialAccessProvider"
import { TranscriptWorkActions } from "./TranscriptWorkActions"

interface FileListToolbarProps {
  caseId: string
  onCreateFolder: () => void
  onDeleteFiles: () => void
}

type UploadMode = "files" | "folder" | "archive"

export function FileListToolbar({
  caseId,
  onCreateFolder,
  onDeleteFiles,
}: FileListToolbarProps) {
  const {
    searchMode,
    setSearchMode,
    fileSearchTerm,
    setFileSearchTerm,
    textSearchTerm,
    setTextSearchTerm,
    openTextSearch,
    statusFilter,
    setStatusFilter,
    typeFilter,
    setTypeFilter,
    selectedFileIds,
    currentFolderId,
    openSidebarTo,
  } = useEvidenceStore()

  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const archiveInputRef = useRef<HTMLInputElement>(null)
  // The pickers open from inside the menu's select (the browser needs the click in the person's gesture), so the menus
  // are closed here: left open, a modal menu keeps the rest of the page hidden from assistive technology.
  const [uploadMenuOpen, setUploadMenuOpen] = useState(false)
  // Opened from the Phones page's "Add a phone report" (Evidence ?add=phone): the menu waits for the person's choice,
  // because the browser opens a file picker only from their own click.
  const [phoneMenuOpen, setPhoneMenuOpen] = useState(() => new URLSearchParams(window.location.search).get("add") === "phone")
  const pick = (
    input: HTMLInputElement | null,
    close: (open: boolean) => void
  ) => {
    input?.click()
    close(false)
  }
  const uploadMutation = useUploadToFolder(caseId)
  // Kept whole as well as destructured, because the dialog takes the gate
  // rather than its pieces. See `ProcessGate`.
  const gate = useGuardedProcess(caseId)
  const { start: startProcess, isChecking, isProcessing } = gate

  const selectionCount = selectedFileIds.size
  const activeSearchTerm =
    searchMode !== "text" ? fileSearchTerm : textSearchTerm
  const setActiveSearchTerm =
    searchMode !== "text" ? setFileSearchTerm : setTextSearchTerm

  const handleUploadSelection = (
    selectedFiles: FileList | null,
    mode: UploadMode
  ) => {
    const files = Array.from(selectedFiles ?? [])
    if (files.length === 0) return

    const uploadFiles = mode === "archive" ? files.slice(0, 1) : files
    const archive = uploadFiles[0]
    if (mode === "archive" && !/\.(zip|ufdr)$/i.test(archive.name)) {
      toast.error("Choose a ZIP file or a phone report file")
      return
    }

    uploadMutation.mutate(
      {
        files: uploadFiles,
        folderId: currentFolderId,
        isFolder: mode === "folder" || mode === "archive",
        isArchive: mode === "archive",
      },
      {
        onSuccess: (result) => {
          if (
            result.task_id ||
            result.task_ids?.length ||
            result.job_ids?.length
          ) {
            openSidebarTo("processing")
          }
          const fallback =
            mode === "archive"
              ? `Uploaded archive ${archive.name}`
              : mode === "folder"
                ? `Uploaded folder with ${uploadFiles.length} file${uploadFiles.length !== 1 ? "s" : ""}`
                : `Uploaded ${uploadFiles.length} file${uploadFiles.length !== 1 ? "s" : ""}`
          toast.success(result.message || fallback)
        },
        onError: (err) => toast.error(err.message),
      }
    )
  }

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleUploadSelection(e.currentTarget.files, "files")
    e.currentTarget.value = ""
  }

  const handleFolderChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleUploadSelection(e.currentTarget.files, "folder")
    e.currentTarget.value = ""
  }

  const handleArchiveChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleUploadSelection(e.currentTarget.files, "archive")
    e.currentTarget.value = ""
  }

  const handleProcess = async () => {
    if (
      (await startProcess({ fileIds: Array.from(selectedFileIds) })) !==
      "started"
    )
      return
    toast.success("Processing started")
    useEvidenceStore.getState().clearSelection()
    useEvidenceStore.getState().openSidebarTo("processing")
  }

  return (
    <div
      className="space-y-2 border-b border-border bg-card px-4 py-2"
      role="group"
      aria-label="Evidence tools"
    >
      <ProcessHoldDialog gate={gate} />
      <div
        className="flex flex-wrap items-center gap-2"
        role="group"
        aria-label="Search and filters"
      >
        {/* One search control, two deliberately different scopes. */}
        <div className="flex min-w-[min(100%,360px)] max-w-[560px] flex-1 basis-[400px] items-center overflow-hidden rounded-md border border-input bg-background shadow-xs transition-[border-color,box-shadow] focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/20">
          <Select
            value={searchMode}
            onValueChange={(value) =>
              setSearchMode(value as "files" | "subtree" | "text")
            }
          >
            <SelectTrigger
              size="sm"
              aria-label="Search scope"
              className="h-8 w-[162px] shrink-0 [&>span]:truncate rounded-none border-0 border-r border-border bg-muted/30 px-2.5 shadow-none focus-visible:ring-0"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent align="start">
              <SelectItem value="files">Files in case</SelectItem>
              <SelectItem value="subtree">
                Files in this folder and subfolders
              </SelectItem>
              <SelectItem value="text">Text in case</SelectItem>
            </SelectContent>
          </Select>
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label={
                searchMode !== "text"
                  ? searchMode === "subtree"
                    ? "Search files in this folder and subfolders"
                    : "Search files in case"
                  : "Search text in case"
              }
              placeholder={
                searchMode !== "text"
                  ? "Search filenames..."
                  : "Find an exact name, phrase, or number..."
              }
              value={activeSearchTerm}
              onFocus={() => searchMode === "text" && openTextSearch()}
              onChange={(e) => setActiveSearchTerm(e.target.value)}
              className="h-8 rounded-none border-0 pl-8 pr-8 text-xs shadow-none focus-visible:ring-0"
            />
          </div>
          {activeSearchTerm && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => setActiveSearchTerm("")}
              className="mr-1.5 flex size-7 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X className="size-3.5" />
            </button>
          )}
        </div>

        {/* Status filter */}
        <Select
          value={statusFilter}
          onValueChange={(v) => setStatusFilter(v as typeof statusFilter)}
        >
          <SelectTrigger
            aria-label="Filter status"
            size="sm"
            className="h-8 w-[130px] text-xs"
          >
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="unprocessed">Unprocessed</SelectItem>
            <SelectItem value="processing">Processing</SelectItem>
            <SelectItem value="processed">Processed</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
            <SelectItem value="awaiting_review">
              Awaiting transcript review
            </SelectItem>
            <SelectItem value="ready">Ready to process audio</SelectItem>
          </SelectContent>
        </Select>

        {/* Type filter */}
        <Select
          value={typeFilter || "all"}
          onValueChange={(v) => setTypeFilter(v === "all" ? "" : v)}
        >
          <SelectTrigger
            aria-label="Filter type"
            size="sm"
            className="h-8 w-[120px] text-xs"
          >
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
      </div>
      <div
        className="flex flex-wrap items-center gap-2"
        role="group"
        aria-label="File actions"
      >
        <TranscriptWorkActions caseId={caseId} />
        <div className="flex-1" />

        {/* Action buttons */}
        <FinancialAccessProvider caseId={caseId} quietFailure>
          <EvidenceFinancialPicker
            caseId={caseId}
            initialFileIds={Array.from(selectedFileIds)}
            initialFolderId={currentFolderId}
            label="Send to Financial review"
            origin="evidence_toolbar"
          />
        </FinancialAccessProvider>
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

        <DropdownMenu open={uploadMenuOpen} onOpenChange={setUploadMenuOpen}>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 gap-1.5 text-xs"
                  disabled={uploadMutation.isPending}
                >
                  <Upload className="size-3.5" />
                  {uploadMutation.isPending ? "Uploading..." : "Upload"}
                  <ChevronDown className="size-3" />
                </Button>
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <TooltipContent>
              Upload files, folders, ZIP archives or phone reports
            </TooltipContent>
          </Tooltip>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuItem
              onSelect={(event) => {
                event.preventDefault()
                pick(fileInputRef.current, setUploadMenuOpen)
              }}
            >
              <Upload className="size-3.5" />
              Files
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={(event) => {
                event.preventDefault()
                pick(folderInputRef.current, setUploadMenuOpen)
              }}
            >
              <FolderUp className="size-3.5" />
              Folder
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={(event) => {
                event.preventDefault()
                pick(archiveInputRef.current, setUploadMenuOpen)
              }}
            >
              <FileArchive className="size-3.5" />
              ZIP file
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        {/* 07 J-1a: the phone start, named without the vendor. Same inputs as Upload; the server detects the report. */}
        <DropdownMenu open={phoneMenuOpen} onOpenChange={setPhoneMenuOpen}>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="h-8 gap-1.5 text-xs"
              disabled={uploadMutation.isPending}
            >
              <Smartphone className="size-3.5" />
              Add phone report (folder or ZIP)
              <ChevronDown className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            <DropdownMenuItem
              onSelect={(event) => {
                event.preventDefault()
                pick(folderInputRef.current, setPhoneMenuOpen)
              }}
            >
              <FolderUp className="size-3.5" />
              Phone report folder
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={(event) => {
                event.preventDefault()
                pick(archiveInputRef.current, setPhoneMenuOpen)
              }}
            >
              <FileArchive className="size-3.5" />
              Phone report ZIP file
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
              The whole report is read and checked against itself when it
              arrives.
            </DropdownMenuLabel>
          </DropdownMenuContent>
        </DropdownMenu>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          disabled={uploadMutation.isPending}
          onChange={handleFileChange}
        />
        <input
          ref={folderInputRef}
          type="file"
          multiple
          className="hidden"
          disabled={uploadMutation.isPending}
          onChange={handleFolderChange}
          {...({
            webkitdirectory: "",
            directory: "",
          } as InputHTMLAttributes<HTMLInputElement>)}
        />
        <input
          ref={archiveInputRef}
          type="file"
          accept=".zip,.ufdr,application/zip,application/x-zip-compressed"
          className="hidden"
          disabled={uploadMutation.isPending}
          onChange={handleArchiveChange}
        />

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="primary"
              size="sm"
              className="h-8 gap-1.5 text-xs"
              disabled={selectionCount === 0 || isChecking || isProcessing}
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

        {selectionCount > 0 && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 text-xs text-red-600 hover:text-red-600 dark:text-red-400 dark:hover:text-red-400"
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
        )}
      </div>
    </div>
  )
}
