import { Music } from "lucide-react"
import { evidenceAPI } from "../../api"

interface AudioPreviewProps {
  evidenceId: string
  filename: string
}

export function AudioPreview({ evidenceId, filename }: AudioPreviewProps) {
  const url = evidenceAPI.getFileUrl(evidenceId)

  return (
    <div className="flex flex-col items-center gap-3 rounded-md bg-muted/30 p-6">
      <Music className="size-8 text-muted-foreground" />
      <audio controls src={url} className="w-full max-w-md">
        Your browser does not support the audio element.
      </audio>
      <p className="text-xs text-muted-foreground">{filename}</p>
    </div>
  )
}
