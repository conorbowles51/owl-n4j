import { useState, type SyntheticEvent } from "react"
import { AlertCircle, FileText, Film, Music, Paperclip, Play } from "lucide-react"

import { DocumentViewer } from "@/components/ui/document-viewer"
import { cn } from "@/lib/cn"

import type { Attachment } from "../../types"
import { attachmentKind, attachmentName, attachmentUrl, videoThumbUrl } from "./commsUtils"

export function CommsAttachments({
  attachments,
  className,
}: {
  attachments: Attachment[]
  className?: string
}) {
  if (attachments.length === 0) return null
  return (
    <div className={cn("mt-2 flex flex-wrap items-start gap-2", className)}>
      {attachments.map((attachment, index) => (
        <CommsAttachment
          key={attachmentKey(attachment, index)}
          attachment={attachment}
          fallbackName={`Attachment ${index + 1}`}
        />
      ))}
    </div>
  )
}

export function CommsAttachment({
  attachment,
  fallbackName = "attachment",
}: {
  attachment: Attachment
  fallbackName?: string
}) {
  const [viewerOpen, setViewerOpen] = useState(false)

  if (!attachment) return null

  const name = attachmentName(attachment, fallbackName)
  const missing = attachment.missing === true
  const url = attachmentUrl(attachment)
  const kind = attachmentKind(attachment)

  if (missing || !url) {
    return (
      <span className="inline-flex max-w-[240px] items-center gap-1.5 rounded-md border border-yellow-500/30 bg-yellow-500/10 px-2 py-1 text-[11px] text-yellow-800 dark:text-yellow-200">
        <AlertCircle className="size-3 shrink-0" />
        <span className="truncate">{name || "Attachment unavailable"}</span>
      </span>
    )
  }

  if (kind === "image") {
    return (
      <>
        <button
          type="button"
          onClick={(event) => openViewer(event, setViewerOpen)}
          onKeyDown={stopPropagation}
          className="block max-w-[260px] overflow-hidden rounded-md border border-border bg-background shadow-sm transition-colors hover:border-amber-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40"
          title={name}
        >
          <img
            src={url}
            alt={name}
            loading="lazy"
            className="max-h-60 max-w-full object-cover"
          />
        </button>
        {viewerOpen && (
          <DocumentViewer
            open={viewerOpen}
            onOpenChange={setViewerOpen}
            documentUrl={url}
            documentName={name}
          />
        )}
      </>
    )
  }

  if (kind === "audio") {
    return (
      <div
        className="flex max-w-[340px] items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5 shadow-sm"
        onClick={stopPropagation}
        onKeyDown={stopPropagation}
      >
        <Music className="size-4 shrink-0 text-amber-500" />
        <audio
          controls
          preload="metadata"
          src={url}
          className="h-8 min-w-[220px] max-w-full"
          aria-label={name}
        />
      </div>
    )
  }

  if (kind === "video") {
    const thumb = videoThumbUrl(attachment)
    return (
      <>
        <button
          type="button"
          onClick={(event) => openViewer(event, setViewerOpen)}
          onKeyDown={stopPropagation}
          className="relative block h-36 w-60 overflow-hidden rounded-md border border-border bg-slate-950 shadow-sm transition-colors hover:border-amber-500/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40"
          title={name}
        >
          {thumb ? (
            <img src={thumb} alt={name} loading="lazy" className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full w-full items-center justify-center bg-muted text-muted-foreground">
              <Film className="size-9" />
            </div>
          )}
          <span className="absolute inset-0 flex items-center justify-center bg-black/25">
            <span className="flex size-10 items-center justify-center rounded-full bg-background/90 text-amber-600 shadow">
              <Play className="ml-0.5 size-5 fill-current" />
            </span>
          </span>
        </button>
        {viewerOpen && (
          <DocumentViewer
            open={viewerOpen}
            onOpenChange={setViewerOpen}
            documentUrl={url}
            documentName={name}
          />
        )}
      </>
    )
  }

  return (
    <>
      <button
        type="button"
        onClick={(event) => openViewer(event, setViewerOpen)}
        onKeyDown={stopPropagation}
        className="inline-flex max-w-[260px] items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1 text-[11px] text-muted-foreground shadow-sm transition-colors hover:border-amber-500/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40"
        title={name}
      >
        {kind === "doc" ? (
          <FileText className="size-3.5 shrink-0" />
        ) : (
          <Paperclip className="size-3.5 shrink-0" />
        )}
        <span className="truncate">{name}</span>
      </button>
      {viewerOpen && (
        <DocumentViewer
          open={viewerOpen}
          onOpenChange={setViewerOpen}
          documentUrl={url}
          documentName={name}
        />
      )}
    </>
  )
}

function attachmentKey(attachment: Attachment, index: number): string {
  return (
    attachmentName(attachment, "") ||
    attachmentUrl(attachment) ||
    String(attachment.file_id ?? attachment.evidence_id ?? index)
  )
}

function openViewer(
  event: SyntheticEvent,
  setViewerOpen: (open: boolean) => void
) {
  event.stopPropagation()
  setViewerOpen(true)
}

function stopPropagation(event: SyntheticEvent) {
  event.stopPropagation()
}
