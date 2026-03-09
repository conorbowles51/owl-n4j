import { useState } from "react"
import { AlertCircle } from "lucide-react"
import { evidenceAPI } from "../../api"

interface ImagePreviewProps {
  evidenceId: string
}

export function ImagePreview({ evidenceId }: ImagePreviewProps) {
  const [error, setError] = useState(false)
  const url = evidenceAPI.getFileUrl(evidenceId)

  if (error) {
    return (
      <div className="flex items-start gap-2 rounded-md bg-red-500/10 p-3">
        <AlertCircle className="mt-0.5 size-4 text-red-400" />
        <p className="text-xs text-muted-foreground">Failed to load image</p>
      </div>
    )
  }

  return (
    <div className="flex justify-center rounded-md bg-muted/30 p-2">
      <img
        src={url}
        alt="Evidence file"
        className="max-h-[500px] max-w-full rounded object-contain"
        onError={() => setError(true)}
      />
    </div>
  )
}
