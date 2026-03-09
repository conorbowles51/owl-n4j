import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Badge } from "@/components/ui/badge"
import { StatusIndicator } from "@/components/ui/status-indicator"
import { Separator } from "@/components/ui/separator"
import { FileText, Calendar, HardDrive, Hash, AlertCircle } from "lucide-react"
import type { EvidenceFile } from "@/types/evidence.types"

interface EvidenceDetailSheetProps {
  file: EvidenceFile | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function DetailRow({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: React.ReactNode }) {
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

export function EvidenceDetailSheet({ file, open, onOpenChange }: EvidenceDetailSheetProps) {
  if (!file) return null

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[400px] overflow-auto">
        <SheetHeader>
          <SheetTitle className="truncate">{file.filename}</SheetTitle>
        </SheetHeader>

        <div className="mt-4 space-y-1">
          <div className="flex items-center gap-2">
            <StatusIndicator status={file.status} />
            <Badge variant="slate">{file.file_type}</Badge>
          </div>

          <Separator className="my-3" />

          <DetailRow icon={HardDrive} label="File size" value={formatSize(file.file_size)} />
          <DetailRow icon={Calendar} label="Uploaded" value={new Date(file.uploaded_at).toLocaleString()} />
          {file.processed_at && (
            <DetailRow icon={Calendar} label="Processed" value={new Date(file.processed_at).toLocaleString()} />
          )}
          <DetailRow
            icon={Hash}
            label="Entities extracted"
            value={file.entity_count !== undefined ? String(file.entity_count) : "—"}
          />

          {file.error_message && (
            <>
              <Separator className="my-3" />
              <div className="flex items-start gap-2 rounded-md bg-red-500/10 p-3">
                <AlertCircle className="mt-0.5 size-4 text-red-400" />
                <div>
                  <p className="text-xs font-medium text-red-400">Processing Error</p>
                  <p className="mt-1 text-xs text-muted-foreground">{file.error_message}</p>
                </div>
              </div>
            </>
          )}

          <Separator className="my-3" />

          <DetailRow icon={FileText} label="File type" value={file.file_type} />
        </div>
      </SheetContent>
    </Sheet>
  )
}
