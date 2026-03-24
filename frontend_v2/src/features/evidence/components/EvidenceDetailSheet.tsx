import { useState } from "react"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { StatusIndicator, type ProcessingStatus } from "@/components/ui/status-indicator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { DocumentViewer } from "@/components/ui/document-viewer"
import {
  FileText,
  Calendar,
  HardDrive,
  Hash,
  AlertCircle,
  RotateCcw,
  Trash2,
  Download,
  Eye,
  ChevronDown,
  ChevronRight,
  Music,
  FolderOpen,
} from "lucide-react"
import type { EvidenceFileRecord } from "@/types/evidence.types"
import { FileSummaryPanel } from "./FileSummaryPanel"
import { evidenceAPI } from "../api"

// File type detection (mirrors FilePreviewPanel)
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

interface EvidenceDetailSheetProps {
  file: EvidenceFileRecord | null
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
  onReprocess?: (file: EvidenceFileRecord) => void
  onDelete?: (file: EvidenceFileRecord) => void
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

export function EvidenceDetailSheet({
  file,
  open,
  onOpenChange,
  caseId,
  onReprocess,
  onDelete,
}: EvidenceDetailSheetProps) {
  const [viewerOpen, setViewerOpen] = useState(false)

  if (!file) return null

  const fileUrl = evidenceAPI.getFileUrl(file.id)
  const ext = getExt(file.original_filename)

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent className="w-[480px] p-0 flex flex-col">
          {/* Header zone */}
          <div className="border-b border-border bg-muted/30 px-6 pb-4 pt-6">
            <SheetHeader className="p-0">
              <div className="flex items-start gap-3">
                <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-amber-500/10">
                  <FileText className="size-5 text-amber-500" />
                </div>
                <div className="min-w-0 flex-1">
                  <SheetTitle className="truncate text-base">
                    {file.original_filename}
                  </SheetTitle>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {ext.toUpperCase() || "File"} &middot; {formatSize(file.size)}
                  </p>
                </div>
              </div>
            </SheetHeader>

            {/* Status row */}
            <div className="mt-3 flex items-center gap-2">
              <StatusIndicator status={file.status as ProcessingStatus} />
              {file.is_duplicate && (
                <Badge variant="warning" className="text-[10px]">
                  Duplicate
                </Badge>
              )}
            </div>

            {/* Action toolbar */}
            <div className="mt-4 flex items-center gap-2">
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
              {onReprocess && file.status !== "processing" && (
                <Button variant="ghost" size="icon-sm" onClick={() => onReprocess(file)} title="Reprocess">
                  <RotateCcw className="size-3.5" />
                </Button>
              )}
              <div className="flex-1" />
              {onDelete && (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-red-500 hover:text-red-600 hover:bg-red-500/10"
                  onClick={() => onDelete(file)}
                  title="Delete"
                >
                  <Trash2 className="size-3.5" />
                </Button>
              )}
            </div>
          </div>

          {/* Scrollable content */}
          <ScrollArea className="flex-1">
            <div className="space-y-4 px-6 py-4">
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
        </SheetContent>
      </Sheet>

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
