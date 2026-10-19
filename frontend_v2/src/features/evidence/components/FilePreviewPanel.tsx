import { File as FileIcon } from "lucide-react"
import { useState } from "react"
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
    return <PdfReadingPreview key={file.id} file={file} />
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

function PdfReadingPreview({ file }: { file: EvidenceFile }) {
  const [reading, setReading] = useState(file.id)
  return <div className="space-y-3">
    {!!file.reading_versions?.length && <details className="rounded border p-3 text-sm">
      <summary className="cursor-pointer font-medium">Reading history · one original PDF</summary>
      <p className="my-2 text-muted-foreground">Loupe retained {file.reading_versions.length} additional {file.reading_versions.length === 1 ? "reading" : "readings"} while preparing Financial statements. These contain the same PDF bytes and are not additional uploads. Earlier readings and their citations remain available.</p>
      <label className="block">PDF version
        <select aria-label="PDF reading version" value={reading} onChange={(event) => setReading(event.target.value)}
          className="ml-2 max-w-full rounded border bg-background p-2">
          <option value={file.id}>Original uploaded PDF</option>
          {file.reading_versions.map((version, index) => <option value={version.id} key={version.id}>
            Reading {index + 1} · {version.created_at ? new Date(version.created_at).toLocaleString() : "Date unavailable"} · {version.status}
          </option>)}
        </select>
      </label>
    </details>}
    <PdfPreview key={reading} evidenceId={reading} />
  </div>
}
