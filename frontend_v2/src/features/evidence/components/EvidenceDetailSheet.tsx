import { useState } from "react"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { StatusIndicator, type ProcessingStatus } from "@/components/ui/status-indicator"
import { Separator } from "@/components/ui/separator"
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
    <div className="flex items-start gap-3 py-2">
      <Icon className="mt-0.5 size-3.5 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-sm text-foreground">{value}</p>
      </div>
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
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 py-2 text-xs font-medium uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
      >
        <Chevron className="size-3.5" />
        {title}
      </button>
      {open && <div className="pb-2">{children}</div>}
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
    <>
      <div className="mt-4">
        {mediaType === "image" && (
          <button
            onClick={onOpenViewer}
            className="group relative w-full overflow-hidden rounded-md border border-border bg-muted/50"
          >
            <img
              src={fileUrl}
              alt={file.original_filename}
              className="w-full max-h-[200px] object-contain"
              loading="lazy"
            />
            <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/30 transition-colors">
              <Eye className="size-6 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          </button>
        )}

        {mediaType === "audio" && (
          <div className="flex flex-col items-center gap-3 rounded-md border border-border bg-muted/50 p-4">
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
          <div className="overflow-hidden rounded-md border border-border bg-black">
            <video
              controls
              src={fileUrl}
              className="w-full max-h-[200px]"
              preload="metadata"
            />
          </div>
        )}
      </div>
      <Separator className="my-4" />
    </>
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
          <div className="px-6 pt-6">
            <SheetHeader>
              <SheetTitle className="truncate text-sm">
                {file.original_filename}
              </SheetTitle>
            </SheetHeader>

            {/* Status row */}
            <div className="mt-3 flex items-center gap-2">
              <StatusIndicator status={file.status as ProcessingStatus} />
              <Badge variant="slate">
                {ext.toUpperCase() || "---"}
              </Badge>
              {file.is_duplicate && (
                <Badge variant="warning" className="text-[10px]">
                  Duplicate
                </Badge>
              )}
            </div>

            {/* Action bar */}
            <div className="mt-3 flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setViewerOpen(true)}
              >
                <Eye className="size-3.5" />
                Open Full File
              </Button>
              <a href={fileUrl} download target="_blank" rel="noopener noreferrer">
                <Button variant="outline" size="sm">
                  <Download className="size-3.5" />
                </Button>
              </a>
              {onReprocess && file.status !== "processing" && (
                <Button variant="outline" size="sm" onClick={() => onReprocess(file)}>
                  <RotateCcw className="size-3.5" />
                </Button>
              )}
              {onDelete && (
                <Button variant="danger" size="sm" onClick={() => onDelete(file)}>
                  <Trash2 className="size-3.5" />
                </Button>
              )}
            </div>
          </div>

          <Separator className="my-4" />

          {/* Scrollable content */}
          <ScrollArea className="flex-1 px-6 pb-6">
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

            <Separator className="my-3" />

            {/* AI Summary section */}
            <CollapsibleSection title="AI Summary">
              <FileSummaryPanel filename={file.original_filename} caseId={caseId} />
            </CollapsibleSection>

            {/* Error card */}
            {file.last_error && (
              <>
                <Separator className="my-3" />
                <div className="flex items-start gap-2 rounded-md bg-red-50 dark:bg-red-500/10 p-3">
                  <AlertCircle className="mt-0.5 size-4 text-red-600 dark:text-red-400" />
                  <div>
                    <p className="text-xs font-medium text-red-600 dark:text-red-400">
                      Processing Error
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">{file.last_error}</p>
                  </div>
                </div>
              </>
            )}
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
