import { evidenceAPI } from "../../api"

interface VideoPreviewProps {
  evidenceId: string
}

export function VideoPreview({ evidenceId }: VideoPreviewProps) {
  const url = evidenceAPI.getFileUrl(evidenceId)

  return (
    <div className="rounded-md bg-black">
      <video
        controls
        src={url}
        className="max-h-[400px] w-full rounded-md"
        preload="metadata"
      >
        Your browser does not support the video element.
      </video>
    </div>
  )
}
