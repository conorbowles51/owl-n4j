import { useState } from "react"
import {
  Info,
  Loader2,
  MessageSquare,
  PanelRightClose,
  FileText,
  Calendar,
  HardDrive,
  Hash,
  AlertCircle,
  Download,
  Eye,
  ChevronDown,
  ChevronRight,
  Music,
  FolderOpen,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { StatusIndicator, type ProcessingStatus } from "@/components/ui/status-indicator"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/cn"
import { useEvidenceStore } from "../evidence.store"
import { JobsPanel } from "./JobsPanel"
import { FileSummaryPanel } from "./FileSummaryPanel"
import { ChatSidePanel } from "@/features/chat/components/ChatSidePanel"
import { evidenceAPI } from "../api"
import type { EvidenceFileRecord } from "@/types/evidence.types"

// --- Shared helpers (mirrored from EvidenceDetailSheet) ---

const IMAGE_EXTS = new Set(["jpg", "jpeg", "png", "gif", "bmp", "svg", "webp"])
const AUDIO_EXTS = new Set(["mp3", "wav", "ogg", "flac", "aac", "m4a"])
const VIDEO_EXTS = new Set(["mp4", "webm", "mov", "avi", "mkv", "flv", "wmv"])

function getExt(filename: string): string {
  return filename.split(".").pop()?.toLowerCase() ?? ""
}

function getMediaType(filename: string): "image" | "audio" | "video" | null {
  const ext = getExt(filename)
  if (IMAGE_EXTS.has(ext)) return "image"
  if (AUDIO_EXTS.has(ext)) return "audio"
  if (VIDEO_EXTS.has(ext)) return "video"
  return null
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function DetailRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType
  label: string
  value: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-3 rounded-md px-1 py-1.5 transition-colors hover:bg-muted/40">
      <Icon className="size-3.5 shrink-0 text-muted-foreground/60" />
      <span className="w-20 shrink-0 text-xs text-muted-foreground">{label}</span>
      <span className="min-w-0 flex-1 text-sm text-foreground">{value}</span>
    </div>
  )
}

function CollapsibleSection({
  title,
  defaultOpen = true,
  children,
}: {
  title: string
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  const Chevron = open ? ChevronDown : ChevronRight

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
      >
        <Chevron className="size-3.5 text-muted-foreground/60" />
        {title}
      </button>
      {open && (
        <div className="border-t border-border px-3 pb-3 pt-1">
          {children}
        </div>
      )}
    </div>
  )
}

function SmartThumbnail({
  file,
  fileUrl,
  onOpenViewer,
}: {
  file: EvidenceFileRecord
  fileUrl: string
  onOpenViewer: () => void
}) {
  const mediaType = getMediaType(file.original_filename)
  if (!mediaType) return null

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      {mediaType === "image" && (
        <button
          onClick={onOpenViewer}
          className="group relative w-full"
        >
          <img
            src={fileUrl}
            alt={file.original_filename}
            className="w-full max-h-[200px] object-contain bg-muted/30"
            loading="lazy"
          />
          <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/30 transition-colors">
            <Eye className="size-6 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
        </button>
      )}

      {mediaType === "audio" && (
        <div className="flex flex-col items-center gap-3 bg-muted/30 p-4">
          <Music className="size-8 text-muted-foreground" />
          <audio
            controls
            src={fileUrl}
            className="w-full"
            preload="metadata"
          />
        </div>
      )}

      {mediaType === "video" && (
        <div className="bg-black">
          <video
            controls
            src={fileUrl}
            className="w-full max-h-[200px]"
            preload="metadata"
          />
        </div>
      )}
    </div>
  )
}

// --- Details panel content (inline version of EvidenceDetailSheet) ---

function DetailsPanelContent({
  file,
  caseId: _caseId,
}: {
  file: EvidenceFileRecord
  caseId: string
}) {
  const [viewerOpen, setViewerOpen] = useState(false)
  const fileUrl = evidenceAPI.getFileUrl(file.id)
  const ext = getExt(file.original_filename)

  return (
    <>
      <ScrollArea className="h-full">
        <div className="space-y-4 p-4">
          {/* Header */}
          <div className="flex items-start gap-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-amber-500/10">
              <FileText className="size-5 text-amber-500" />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="truncate text-sm font-semibold">
                {file.original_filename}
              </h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {ext.toUpperCase() || "File"} &middot; {formatSize(file.size)}
              </p>
            </div>
          </div>

          {/* Status row */}
          <div className="flex items-center gap-2">
            <StatusIndicator status={file.status as ProcessingStatus} />
            {file.is_duplicate && (
              <Badge variant="warning" className="text-[10px]">
                Duplicate
              </Badge>
            )}
          </div>

          {/* Action toolbar */}
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={() => setViewerOpen(true)}
            >
              <Eye className="size-3.5" />
              Open File
            </Button>
            <a href={fileUrl} download target="_blank" rel="noopener noreferrer">
              <Button variant="ghost" size="icon-sm" title="Download">
                <Download className="size-3.5" />
              </Button>
            </a>
          </div>

          {/* Smart thumbnail */}
          <SmartThumbnail
            file={file}
            fileUrl={fileUrl}
            onOpenViewer={() => setViewerOpen(true)}
          />

          {/* Details section */}
          <CollapsibleSection title="Details">
            <DetailRow icon={HardDrive} label="File size" value={formatSize(file.size)} />
            <DetailRow
              icon={Calendar}
              label="Uploaded"
              value={file.created_at ? new Date(file.created_at).toLocaleString() : "---"}
            />
            {file.processed_at && (
              <DetailRow
                icon={Calendar}
                label="Processed"
                value={new Date(file.processed_at).toLocaleString()}
              />
            )}
            {file.folder_id && (
              <DetailRow
                icon={FolderOpen}
                label="Folder"
                value={file.folder_id}
              />
            )}
            <DetailRow
              icon={Hash}
              label="SHA-256"
              value={
                <span className="break-all font-mono text-[10px]">
                  {file.sha256}
                </span>
              }
            />
          </CollapsibleSection>

          {/* AI Summary section */}
          <CollapsibleSection title="AI Summary">
            <FileSummaryPanel summary={file.summary} />
          </CollapsibleSection>

          {/* Error card */}
          {file.last_error && (
            <div className="overflow-hidden rounded-lg border border-red-200 bg-red-50 dark:border-red-500/20 dark:bg-red-500/5">
              <div className="flex items-start gap-3 p-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-red-500/10">
                  <AlertCircle className="size-4 text-red-500" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold text-red-600 dark:text-red-400">
                    Processing Error
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {file.last_error}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Document Viewer modal */}
      <DocumentViewer
        open={viewerOpen}
        onOpenChange={setViewerOpen}
        documentUrl={fileUrl}
        documentName={file.original_filename}
      />
    </>
  )
}

// --- Main sidebar component ---

interface EvidenceContextSidebarProps {
  caseId: string
  detailFile: EvidenceFileRecord | null
}

export function EvidenceContextSidebar({
  caseId,
  detailFile,
}: EvidenceContextSidebarProps) {
  const { sidebarTab, setSidebarTab, setSidebarOpen } = useEvidenceStore()

  const tabs = [
    { id: "details" as const, label: "Details", icon: Info },
    { id: "processing" as const, label: "Processing", icon: Loader2 },
    { id: "chat" as const, label: "AI Chat", icon: MessageSquare },
  ]

  return (
    <div className="flex h-full flex-col border-l border-border bg-card">
      {/* Tab bar */}
      <div className="flex items-center border-b border-border bg-muted/30">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setSidebarTab(tab.id)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 text-xs font-medium transition-colors border-b-2",
              sidebarTab === tab.id
                ? "border-amber-500 text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <tab.icon className="size-3.5" />
            {tab.label}
          </button>
        ))}
        <div className="ml-auto pr-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setSidebarOpen(false)}
              >
                <PanelRightClose className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">Collapse panel</TooltipContent>
          </Tooltip>
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {sidebarTab === "details" && (
          detailFile ? (
            <DetailsPanelContent file={detailFile} caseId={caseId} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
              <Info className="size-8 text-muted-foreground/40" />
              <p className="text-sm font-medium text-muted-foreground">
                Select a file to view details
              </p>
              <p className="text-xs text-muted-foreground/70">
                Click a filename in the file list
              </p>
            </div>
          )
        )}
        {sidebarTab === "processing" && (
          <JobsPanel caseId={caseId} />
        )}
        {sidebarTab === "chat" && (
          <ChatSidePanel caseId={caseId} />
        )}
      </div>
    </div>
  )
}
