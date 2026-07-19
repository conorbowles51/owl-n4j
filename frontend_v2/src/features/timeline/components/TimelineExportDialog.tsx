import { useEffect, useMemo, useState } from "react"
import { Download, FileSpreadsheet, FileText } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { timelineAPI, type TimelineEvent } from "../api"
import {
  TIMELINE_EXPORT_FIELDS,
  buildTimelineExportPayload,
  defaultTimelineExportFields,
  timelineDateSpan,
  type TimelineExportDetailLevel,
  type TimelineExportFields,
  type TimelineExportFormat,
  type TimelineExportSource,
} from "../lib/timeline-export"

interface TimelineExportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
  filteredEvents: TimelineEvent[]
  selectedKeys: Set<string>
  preferredSource?: TimelineExportSource | null
}

function downloadBlob(blob: Blob, filename: string) {
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = objectUrl
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
}

export function TimelineExportDialog({
  open,
  onOpenChange,
  caseId,
  filteredEvents,
  selectedKeys,
  preferredSource,
}: TimelineExportDialogProps) {
  const [source, setSource] = useState<TimelineExportSource>("filtered")
  const [format, setFormat] = useState<TimelineExportFormat>("pdf")
  const [detailLevel, setDetailLevel] = useState<TimelineExportDetailLevel>("standard")
  const [fields, setFields] = useState<TimelineExportFields>(
    defaultTimelineExportFields("standard")
  )
  const [title, setTitle] = useState("")
  const [isDownloading, setIsDownloading] = useState(false)

  useEffect(() => {
    if (!open) return
    setSource(preferredSource ?? (selectedKeys.size > 0 ? "selection" : "filtered"))
    setTitle("Timeline Export")
  }, [open, preferredSource, selectedKeys.size])

  const selectedCount = selectedKeys.size
  const sourceCount = useMemo(() => {
    if (source === "selection") return selectedCount
    return filteredEvents.length
  }, [filteredEvents.length, selectedCount, source])

  const previewSpan = timelineDateSpan(filteredEvents)
  const tooLargeForPdf = format === "pdf" && sourceCount > 5000
  const canExport =
    sourceCount > 0 &&
    !tooLargeForPdf &&
    (source !== "selection" || selectedCount > 0)

  const handleDetailChange = (value: TimelineExportDetailLevel) => {
    setDetailLevel(value)
    setFields(defaultTimelineExportFields(value))
  }

  const toggleField = (key: keyof TimelineExportFields) => {
    setFields((current) => ({ ...current, [key]: !current[key] }))
  }

  const handleExport = async () => {
    if (!canExport) return
    setIsDownloading(true)
    try {
      const payload = buildTimelineExportPayload({
        caseId,
        source,
        format,
        detailLevel,
        fields,
        activeView: null,
        filteredEvents,
        selectedKeys,
        title,
      })
      const { blob, filename } = await timelineAPI.downloadExport(payload)
      downloadBlob(blob, filename)
      toast.success(`${format.toUpperCase()} export downloaded`)
      onOpenChange(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Timeline export failed")
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(calc(100vw-2rem),64rem)] max-w-none sm:max-w-none">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Download className="size-4" />
            Export Timeline
          </DialogTitle>
        </DialogHeader>

        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs font-medium">Title</label>
              <Input value={title} onChange={(event) => setTitle(event.target.value)} />
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <label className="mb-1 block text-xs font-medium">Source</label>
                <Select value={source} onValueChange={(value) => setSource(value as TimelineExportSource)}>
                  <SelectTrigger className="h-8 w-full text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="filtered">Current filters ({filteredEvents.length})</SelectItem>
                    <SelectItem value="selection" disabled={selectedCount === 0}>
                      Selected events ({selectedCount})
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium">Format</label>
                <Select value={format} onValueChange={(value) => setFormat(value as TimelineExportFormat)}>
                  <SelectTrigger className="h-8 w-full text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pdf">PDF</SelectItem>
                    <SelectItem value="csv">CSV</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium">Detail</label>
                <Select
                  value={detailLevel}
                  onValueChange={(value) => handleDetailChange(value as TimelineExportDetailLevel)}
                >
                  <SelectTrigger className="h-8 w-full text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="compact">Compact</SelectItem>
                    <SelectItem value="standard">Standard</SelectItem>
                    <SelectItem value="detailed">Detailed</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="rounded-md border border-border">
              <div className="border-b border-border px-3 py-2 text-xs font-semibold">
                Include
              </div>
              <div className="grid gap-1 p-2 sm:grid-cols-2 lg:grid-cols-3">
                {TIMELINE_EXPORT_FIELDS.map((field) => (
                  <div
                    key={field.key}
                    role="button"
                    tabIndex={0}
                    onClick={() => toggleField(field.key)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault()
                        toggleField(field.key)
                      }
                    }}
                    className="flex items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-muted"
                  >
                    <Checkbox checked={fields[field.key]} />
                    <span>{field.label}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <aside className="rounded-md border border-border bg-muted/20 p-3">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
              {format === "pdf" ? (
                <FileText className="size-4 text-amber-600" />
              ) : (
                <FileSpreadsheet className="size-4 text-emerald-600" />
              )}
              {format.toUpperCase()}
            </div>
            <dl className="space-y-2 text-xs">
              <div>
                <dt className="text-muted-foreground">Events</dt>
                <dd className="font-semibold">{sourceCount}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Date span</dt>
                <dd className="font-semibold">{previewSpan}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Sources</dt>
                <dd className="font-semibold">
                  {fields.source_references ? "Appendix" : "Not included"}
                </dd>
              </div>
            </dl>
            {tooLargeForPdf && (
              <p className="mt-3 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                Use CSV for exports over 5,000 events.
              </p>
            )}
          </aside>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleExport} disabled={!canExport || isDownloading}>
            {isDownloading ? "Preparing..." : "Download"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
