import { useState, useEffect, useRef } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  Film,
  Music,
  Loader2,
} from "lucide-react"

const IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".tif"]
const AUDIO_EXTS = [".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma"]
const VIDEO_EXTS = [".mp4", ".webm", ".mov", ".avi", ".mkv", ".flv", ".wmv"]
const PDF_EXTS = [".pdf"]
const TEXT_EXTS = [".txt", ".md", ".json", ".xml", ".csv", ".log", ".rtf"]

function getFileType(filename: string | undefined) {
  if (!filename) return "unknown"
  const ext = ("." + filename.split(".").pop()).toLowerCase()
  if (PDF_EXTS.includes(ext)) return "pdf"
  if (IMAGE_EXTS.includes(ext)) return "image"
  if (AUDIO_EXTS.includes(ext)) return "audio"
  if (VIDEO_EXTS.includes(ext)) return "video"
  if (TEXT_EXTS.includes(ext)) return "text"
  return "unknown"
}

const FILE_ICONS: Record<string, typeof FileText> = {
  image: ImageIcon,
  audio: Music,
  video: Film,
}

interface DocumentViewerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  documentUrl?: string
  documentName?: string
  initialPage?: number
}

export function DocumentViewer({
  open,
  onOpenChange,
  documentUrl,
  documentName,
  initialPage = 1,
}: DocumentViewerProps) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [currentPage, setCurrentPage] = useState(initialPage)
  const [textContent, setTextContent] = useState<string | null>(null)
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const fetchIdRef = useRef(0)

  const fileType = getFileType(documentName)
  const IconComp = FILE_ICONS[fileType] ?? FileText
  const isPdf = fileType === "pdf"

  // Reset and fetch when dialog opens
  useEffect(() => {
    if (!open) return
    setLoading(true)
    setError(null)
    setCurrentPage(initialPage)
    setTextContent(null)

    if (documentUrl && fileType === "text") {
      const id = ++fetchIdRef.current
      fetch(documentUrl)
        .then((res) => {
          if (!res.ok) throw new Error("Failed to load")
          return res.text()
        })
        .then((text) => {
          if (id === fetchIdRef.current) {
            setTextContent(text)
            setLoading(false)
          }
        })
        .catch(() => {
          if (id === fetchIdRef.current) {
            setError("Failed to load text document")
            setLoading(false)
          }
        })
    } else if (documentUrl && (fileType === "image" || fileType === "audio" || fileType === "video")) {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, documentUrl, fileType])

  const pdfUrlWithPage = documentUrl && isPdf ? `${documentUrl}#page=${currentPage}` : null

  const handleOpenInNewTab = () => {
    if (documentUrl) window.open(isPdf ? pdfUrlWithPage : documentUrl, "_blank")
  }

  const renderContent = () => {
    if (!documentUrl) {
      return (
        <div className="flex h-full items-center justify-center">
          <div className="flex flex-col items-center gap-3 text-center p-6">
            <FileText className="size-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">No document selected</p>
          </div>
        </div>
      )
    }

    switch (fileType) {
      case "image":
        return (
          <div className="flex h-full items-center justify-center bg-muted/50 p-4 overflow-auto">
            <img
              src={documentUrl}
              alt={documentName}
              className="max-w-full max-h-full object-contain rounded shadow-lg"
              onLoad={() => setLoading(false)}
              onError={() => { setLoading(false); setError("Failed to load image") }}
            />
          </div>
        )

      case "audio":
        return (
          <div className="flex h-full items-center justify-center">
            <div className="flex flex-col items-center gap-4 p-8">
              <Music className="size-12 text-muted-foreground" />
              <p className="text-sm font-medium">{documentName}</p>
              <audio
                controls
                src={documentUrl}
                className="w-full max-w-md"
                onCanPlay={() => setLoading(false)}
                onError={() => { setLoading(false); setError("Failed to load audio") }}
                preload="metadata"
              />
            </div>
          </div>
        )

      case "video":
        return (
          <div className="flex h-full items-center justify-center bg-black p-4">
            <video
              controls
              src={documentUrl}
              className="max-w-full max-h-full rounded"
              onCanPlay={() => setLoading(false)}
              onError={() => { setLoading(false); setError("Failed to load video") }}
              preload="metadata"
            />
          </div>
        )

      case "text":
        return (
          <div className="h-full overflow-auto bg-background p-6">
            {textContent !== null && (
              <pre className="text-sm text-foreground whitespace-pre-wrap font-mono leading-relaxed">
                {textContent}
              </pre>
            )}
          </div>
        )

      case "pdf":
        return (
          <iframe
            ref={iframeRef}
            src={pdfUrlWithPage!}
            className="h-full w-full border-0"
            onLoad={() => setLoading(false)}
            onError={() => { setLoading(false); setError("Failed to load document") }}
            title={documentName || "Document"}
          />
        )

      default:
        return (
          <iframe
            ref={iframeRef}
            src={documentUrl}
            className="h-full w-full border-0"
            onLoad={() => setLoading(false)}
            onError={() => { setLoading(false); setError("Failed to load document") }}
            title={documentName || "Document"}
          />
        )
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl h-[85vh] flex flex-col p-0 gap-0" showCloseButton={false}>
        <DialogHeader className="flex-row items-center justify-between border-b border-border px-4 py-3 space-y-0">
          <div className="flex items-center gap-3">
            <IconComp className="size-5 text-muted-foreground" />
            <DialogTitle className="text-base">
              {documentName || "Document Viewer"}
            </DialogTitle>
          </div>
          <div className="flex items-center gap-1">
            {isPdf && (
              <div className="flex items-center gap-1 mr-2">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                >
                  <ChevronLeft className="size-4" />
                </Button>
                <span className="text-xs text-muted-foreground min-w-[60px] text-center">
                  Page {currentPage}
                </span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setCurrentPage(currentPage + 1)}
                >
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            )}
            <Button variant="ghost" size="icon-sm" onClick={handleOpenInNewTab} title="Open in new tab">
              <ExternalLink className="size-4" />
            </Button>
          </div>
        </DialogHeader>

        <div className="flex-1 relative overflow-hidden">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-background">
              <div className="flex flex-col items-center gap-3">
                <Loader2 className="size-8 text-muted-foreground animate-spin" />
                <p className="text-sm text-muted-foreground">Loading {fileType}...</p>
              </div>
            </div>
          )}

          {error && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-background">
              <div className="flex flex-col items-center gap-3 text-center p-6">
                <FileText className="size-8 text-destructive" />
                <p className="text-sm font-medium">Failed to load {fileType}</p>
                <Button variant="outline" size="sm" onClick={handleOpenInNewTab}>
                  <ExternalLink className="size-3.5 mr-1.5" />
                  Try opening in new tab
                </Button>
              </div>
            </div>
          )}

          {renderContent()}
        </div>
      </DialogContent>
    </Dialog>
  )
}
