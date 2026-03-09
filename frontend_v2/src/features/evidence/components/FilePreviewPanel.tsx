import { FileText, Image, Music, Film, File as FileIcon } from "lucide-react"
import type { EvidenceFile } from "@/types/evidence.types"
import { TextPreview } from "./previews/TextPreview"
import { ImagePreview } from "./previews/ImagePreview"
import { AudioPreview } from "./previews/AudioPreview"
import { VideoPreview } from "./previews/VideoPreview"
import { PdfPreview } from "./previews/PdfPreview"

const TEXT_EXTS = new Set(["txt", "md", "json", "xml", "csv", "log", "rtf", "sri"])
const IMAGE_EXTS = new Set(["jpg", "jpeg", "png", "gif", "bmp", "svg", "webp"])
const AUDIO_EXTS = new Set(["mp3", "wav", "ogg", "flac", "aac", "m4a"])
const VIDEO_EXTS = new Set(["mp4", "webm", "mov", "avi", "mkv", "flv", "wmv"])
const PDF_EXTS = new Set(["pdf"])

function getExt(filename: string): string {
  return filename.split(".").pop()?.toLowerCase() ?? ""
}

interface FilePreviewPanelProps {
  file: EvidenceFile
  caseId: string
}

export function FilePreviewPanel({ file, caseId }: FilePreviewPanelProps) {
  const ext = getExt(file.original_filename)

  if (TEXT_EXTS.has(ext)) {
    return <TextPreview file={file} caseId={caseId} />
  }

  if (IMAGE_EXTS.has(ext)) {
    return <ImagePreview evidenceId={file.id} />
  }

  if (AUDIO_EXTS.has(ext)) {
    return <AudioPreview evidenceId={file.id} filename={file.original_filename} />
  }

  if (VIDEO_EXTS.has(ext)) {
    return <VideoPreview evidenceId={file.id} />
  }

  if (PDF_EXTS.has(ext)) {
    return <PdfPreview evidenceId={file.id} />
  }

  return (
    <div className="flex flex-col items-center gap-2 py-8">
      <FileIcon className="size-8 text-muted-foreground/40" />
      <p className="text-xs text-muted-foreground">
        Preview not available for .{ext || "unknown"} files
      </p>
    </div>
  )
}

export function getFileTypeIcon(filename: string) {
  const ext = getExt(filename)
  if (TEXT_EXTS.has(ext)) return FileText
  if (IMAGE_EXTS.has(ext)) return Image
  if (AUDIO_EXTS.has(ext)) return Music
  if (VIDEO_EXTS.has(ext)) return Film
  return FileIcon
}

export function isVideoFile(filename: string) {
  return VIDEO_EXTS.has(getExt(filename))
}
