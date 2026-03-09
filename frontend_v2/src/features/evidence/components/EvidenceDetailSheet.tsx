import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { StatusIndicator, type ProcessingStatus } from "@/components/ui/status-indicator"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
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
  Sparkles,
  Film,
} from "lucide-react"
import type { EvidenceFile } from "@/types/evidence.types"
import { FilePreviewPanel, isVideoFile } from "./FilePreviewPanel"
import { FileSummaryPanel } from "./FileSummaryPanel"
import { VideoFramesGrid } from "./previews/VideoFramesGrid"
import { evidenceAPI } from "../api"

interface EvidenceDetailSheetProps {
  file: EvidenceFile | null
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
  onReprocess?: (file: EvidenceFile) => void
  onDelete?: (file: EvidenceFile) => void
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

export function EvidenceDetailSheet({
  file,
  open,
  onOpenChange,
  caseId,
  onReprocess,
  onDelete,
}: EvidenceDetailSheetProps) {
  if (!file) return null

  const isVideo = isVideoFile(file.original_filename)
  const fileUrl = evidenceAPI.getFileUrl(file.id)

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[480px] overflow-auto">
        <SheetHeader>
          <SheetTitle className="truncate text-sm">{file.original_filename}</SheetTitle>
        </SheetHeader>

        <div className="mt-3 flex items-center gap-2">
          <StatusIndicator status={file.status as ProcessingStatus} />
          <Badge variant="slate">
            {file.original_filename.split(".").pop()?.toUpperCase() ?? "—"}
          </Badge>
          {file.duplicate_of && (
            <Badge variant="warning" className="text-[10px]">
              Duplicate
            </Badge>
          )}
        </div>

        {/* Action buttons */}
        <div className="mt-3 flex gap-2">
          <a href={fileUrl} download target="_blank" rel="noopener noreferrer">
            <Button variant="outline" size="sm">
              <Download className="size-3.5" />
              Download
            </Button>
          </a>
          {onReprocess && file.status !== "processing" && (
            <Button variant="outline" size="sm" onClick={() => onReprocess(file)}>
              <RotateCcw className="size-3.5" />
              Reprocess
            </Button>
          )}
          {onDelete && (
            <Button variant="danger" size="sm" onClick={() => onDelete(file)}>
              <Trash2 className="size-3.5" />
              Delete
            </Button>
          )}
        </div>

        <Separator className="my-4" />

        <Tabs defaultValue="info" className="w-full">
          <TabsList variant="line" className="w-full">
            <TabsTrigger value="info">
              <FileText className="size-3" />
              Info
            </TabsTrigger>
            <TabsTrigger value="preview">
              <Eye className="size-3" />
              Preview
            </TabsTrigger>
            <TabsTrigger value="summary">
              <Sparkles className="size-3" />
              Summary
            </TabsTrigger>
            {isVideo && (
              <TabsTrigger value="frames">
                <Film className="size-3" />
                Frames
              </TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="info" className="mt-3 space-y-1">
            <DetailRow icon={HardDrive} label="File size" value={formatSize(file.size)} />
            <DetailRow
              icon={Calendar}
              label="Uploaded"
              value={new Date(file.created_at).toLocaleString()}
            />
            {file.processed_at && (
              <DetailRow
                icon={Calendar}
                label="Processed"
                value={new Date(file.processed_at).toLocaleString()}
              />
            )}
            <DetailRow
              icon={Hash}
              label="Entities extracted"
              value={file.entity_count !== undefined ? String(file.entity_count) : "—"}
            />
            <DetailRow
              icon={FileText}
              label="SHA-256"
              value={
                <span className="break-all font-mono text-[10px]">
                  {file.sha256}
                </span>
              }
            />

            {file.last_error && (
              <>
                <Separator className="my-3" />
                <div className="flex items-start gap-2 rounded-md bg-red-500/10 p-3">
                  <AlertCircle className="mt-0.5 size-4 text-red-400" />
                  <div>
                    <p className="text-xs font-medium text-red-400">Processing Error</p>
                    <p className="mt-1 text-xs text-muted-foreground">{file.last_error}</p>
                  </div>
                </div>
              </>
            )}
          </TabsContent>

          <TabsContent value="preview" className="mt-3">
            <FilePreviewPanel file={file} caseId={caseId} />
          </TabsContent>

          <TabsContent value="summary" className="mt-3">
            <FileSummaryPanel filename={file.original_filename} caseId={caseId} />
          </TabsContent>

          {isVideo && (
            <TabsContent value="frames" className="mt-3">
              <VideoFramesGrid evidenceId={file.id} />
            </TabsContent>
          )}
        </Tabs>
      </SheetContent>
    </Sheet>
  )
}
