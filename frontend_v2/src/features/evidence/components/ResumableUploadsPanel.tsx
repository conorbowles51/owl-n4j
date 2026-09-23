import { useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import {
  pauseUpload,
  resumeUpload,
  hasLocalUploadFile,
  type UploadSession,
} from "../resumable-upload"
import { useResumableUploads } from "../use-resumable-uploads"

function UploadRow({ upload }: { upload: UploadSession }) {
  const picker = useRef<HTMLInputElement>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const queryClient = useQueryClient()
  const received = upload.received.reduce(
    (sum, index) =>
      sum +
      Math.min(upload.chunk_size, upload.size - index * upload.chunk_size),
    0
  )
  const refresh = () => {
    queryClient.invalidateQueries({
      queryKey: ["resumable-uploads", upload.case_id],
    })
    queryClient.invalidateQueries({
      queryKey: ["evidence-folder-contents", upload.case_id],
    })
    queryClient.invalidateQueries({ queryKey: ["evidence", upload.case_id] })
  }
  const resume = async (file?: File) => {
    setError("")
    setBusy(true)
    try {
      await resumeUpload(upload.id, file)
      refresh()
    } catch (cause) {
      setError((cause as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const attached = hasLocalUploadFile(upload.id)
  return (
    <div className="rounded-lg border p-3 space-y-2">
      <p className="text-sm font-medium break-words">{upload.filename}</p>
      <p className="text-xs">
        {upload.status === "paused"
          ? "Upload paused"
          : attached
            ? "Uploading"
            : "Upload interrupted — reselect the file to resume"}
      </p>
      <Progress value={upload.size ? (received / upload.size) * 100 : 100} />
      <p className="text-xs text-muted-foreground">
        {(received / 1048576).toFixed(1)} of{" "}
        {(upload.size / 1048576).toFixed(1)} MB saved. Ingestion starts after
        upload.
      </p>
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        {upload.status !== "paused" && attached ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void pauseUpload(upload.id)
                .then(refresh)
                .catch((cause) => setError(cause.message))
            }}
          >
            Pause upload
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            disabled={busy && !attached}
            onClick={() => (attached ? void resume() : picker.current?.click())}
          >
            {attached ? "Resume upload" : "Reselect file to resume"}
          </Button>
        )}
      </div>
      <input
        ref={picker}
        type="file"
        className="sr-only"
        aria-label={`Original file for ${upload.filename}`}
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) void resume(file)
          event.target.value = ""
        }}
      />
    </div>
  )
}

export function ResumableUploadsPanel({ caseId }: { caseId: string }) {
  const { data } = useResumableUploads(caseId)
  return (
    <>
      {data?.map((upload) => (
        <UploadRow key={upload.id} upload={upload} />
      ))}
    </>
  )
}
