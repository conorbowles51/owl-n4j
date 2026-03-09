import { useState } from "react"
import { Camera, ChevronLeft, ChevronRight, X } from "lucide-react"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { evidenceAPI } from "../../api"
import { useVideoFrames } from "../../hooks/use-evidence-detail"
import type { VideoFrame } from "@/types/evidence.types"

interface VideoFramesGridProps {
  evidenceId: string
}

export function VideoFramesGrid({ evidenceId }: VideoFramesGridProps) {
  const { data: frames, isLoading, error } = useVideoFrames(evidenceId)
  const [selectedFrame, setSelectedFrame] = useState<VideoFrame | null>(null)

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-8">
        <LoadingSpinner size="sm" />
        <span className="text-xs text-muted-foreground">Extracting video frames...</span>
      </div>
    )
  }

  if (error) {
    return (
      <p className="py-4 text-center text-xs text-muted-foreground">
        Failed to extract frames
      </p>
    )
  }

  if (!frames?.length) {
    return (
      <div className="flex flex-col items-center gap-2 py-6">
        <Camera className="size-8 text-muted-foreground/40" />
        <p className="text-xs text-muted-foreground">No frames extracted</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {selectedFrame && (
        <div className="relative overflow-hidden rounded-md bg-black">
          <img
            src={evidenceAPI.getVideoFrameUrl(evidenceId, selectedFrame.filename)}
            alt={`Frame at ${selectedFrame.timestamp_str}`}
            className="mx-auto max-h-[240px] object-contain"
          />
          <div className="absolute bottom-0 left-0 right-0 flex items-center justify-between bg-gradient-to-t from-black/70 to-transparent px-3 py-2">
            <span className="text-xs text-white font-mono">
              {selectedFrame.timestamp_str} — Frame {selectedFrame.frame_number}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => {
                  const idx = frames.findIndex((f) => f.frame_number === selectedFrame.frame_number)
                  if (idx > 0) setSelectedFrame(frames[idx - 1])
                }}
                className="rounded p-1 text-white/80 hover:text-white disabled:text-white/30"
                disabled={selectedFrame.frame_number === frames[0].frame_number}
              >
                <ChevronLeft className="size-4" />
              </button>
              <button
                onClick={() => {
                  const idx = frames.findIndex((f) => f.frame_number === selectedFrame.frame_number)
                  if (idx < frames.length - 1) setSelectedFrame(frames[idx + 1])
                }}
                className="rounded p-1 text-white/80 hover:text-white disabled:text-white/30"
                disabled={selectedFrame.frame_number === frames[frames.length - 1].frame_number}
              >
                <ChevronRight className="size-4" />
              </button>
              <button
                onClick={() => setSelectedFrame(null)}
                className="ml-1 rounded p-1 text-white/80 hover:text-white"
              >
                <X className="size-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        <Camera className="size-3" />
        <span>{frames.length} frame{frames.length !== 1 ? "s" : ""}</span>
      </div>

      <div className="grid grid-cols-4 gap-1.5">
        {frames.map((frame) => (
          <button
            key={frame.frame_number}
            onClick={() => setSelectedFrame(frame)}
            className={`group relative overflow-hidden rounded border transition-all ${
              selectedFrame?.frame_number === frame.frame_number
                ? "border-amber-500 ring-1 ring-amber-500/30"
                : "border-border hover:border-muted-foreground/50"
            }`}
          >
            <img
              src={evidenceAPI.getVideoFrameUrl(evidenceId, frame.filename)}
              alt={`Frame ${frame.frame_number}`}
              className="aspect-video w-full object-cover"
              loading="lazy"
            />
            <div className="absolute bottom-0 left-0 right-0 bg-black/60 px-1 py-0.5">
              <span className="font-mono text-[9px] text-white">{frame.timestamp_str}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
