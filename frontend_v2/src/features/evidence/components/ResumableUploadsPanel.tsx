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
import {
  useResumableUploads,
  useResumableUploadGroups,
} from "../use-resumable-uploads"
import {
  hasLocalUploadGroup,
  isCompletingUploadGroup,
  pauseUploadGroup,
  resumeUploadGroup,
  type UploadGroup,
} from "../resumable-upload-groups"
import { toast } from "sonner"

function GroupRow({ group }: { group: UploadGroup }) {
  const picker = useRef<HTMLInputElement>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const client = useQueryClient()
  const attached = hasLocalUploadGroup(group.id)
  const completing = isCompletingUploadGroup(group.id)
  const allSaved = group.staged_count === group.file_count
  const refresh = () => {
    for (const key of [
      "resumable-upload-groups",
      "evidence-folder-tree",
      "evidence-folder-contents",
      "evidence",
      "evidence-jobs",
      "background-tasks",
      "statement-import-files",
    ])
      void client.invalidateQueries({ queryKey: [key, group.case_id] })
  }
  const resume = async (files?: File[]) => {
    setError("")
    setBusy(true)
    try {
      const result = await resumeUploadGroup(group.id, files)
      toast.success(result.receipt?.message || "Upload complete")
      refresh()
    } catch (cause) {
      setError((cause as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="rounded-lg border p-3 space-y-2">
      <p className="text-sm font-medium break-words">{group.name}</p>
      <p className="text-xs">
        {completing
          ? "Files received — finishing registration"
          : group.status === "dispatching"
            ? "Files saved — processing needs to be connected"
            : group.status === "paused"
              ? "Upload paused"
              : attached
                ? "Uploading selection"
                : allSaved
                  ? "Files received — finish registration"
                  : "Upload interrupted — reselect to resume"}
      </p>
      <Progress
        value={group.size ? (group.received_bytes / group.size) * 100 : 100}
      />
      <p className="text-xs text-muted-foreground">
        {group.staged_count} of {group.file_count} files verified ·{" "}
        {(group.received_bytes / 1048576).toFixed(1)} of{" "}
        {(group.size / 1048576).toFixed(1)} MB saved.
      </p>
      <p className="text-xs text-muted-foreground">
        Your selection and received parts are kept. After an interruption, only
        missing parts are sent.{" "}
        {group.kind === "archive"
          ? "The archive is unpacked after upload."
          : "Files appear in Evidence when the complete selection is registered."}
      </p>
      {error && (
        <p role="alert" className="text-xs text-destructive break-words">
          {error}
        </p>
      )}
      {completing ? (
        <p className="text-xs" role="status">
          You can leave this screen. A saved receipt prevents repeated files.
        </p>
      ) : group.status === "uploading" && attached ? (
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            void pauseUploadGroup(group.id)
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
          onClick={() =>
            attached || allSaved ? void resume() : picker.current?.click()
          }
        >
          {allSaved
            ? "Finish registration"
            : attached
              ? "Resume upload"
              : group.kind === "folder"
                ? "Reselect folder to resume"
                : group.kind === "files"
                  ? "Reselect files to resume"
                  : "Reselect archive to resume"}
        </Button>
      )}
      <input
        ref={(node) => {
          picker.current = node
          if (node && group.kind === "folder")
            node.setAttribute("webkitdirectory", "")
        }}
        type="file"
        multiple={group.kind !== "archive"}
        accept={group.kind === "archive" ? ".zip" : undefined}
        className="sr-only"
        aria-label={`Original ${group.kind} for ${group.name}`}
        onChange={(event) => {
          const files = Array.from(event.target.files || [])
          if (files.length) void resume(files)
          event.target.value = ""
        }}
      />
    </div>
  )
}

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
    queryClient.invalidateQueries({
      queryKey: ["statement-import-files", upload.case_id],
    })
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

export function ResumableUploadsPanel({
  caseId,
  financialContext = false,
  active = true,
}: {
  caseId: string
  financialContext?: boolean
  active?: boolean
}) {
  const { data } = useResumableUploads(caseId, active)
  const { data: groups } = useResumableUploadGroups(caseId, active)
  return (
    <>
      {financialContext && (!!groups?.length || !!data?.length) && (
        <p className="text-sm text-muted-foreground">
          Evidence upload activity for this case. These uploads only appear in
          the Financial file list when you choose them for financial review.
        </p>
      )}
      {groups?.map((group) => (
        <GroupRow key={group.id} group={group} />
      ))}
      {data?.map((upload) => (
        <UploadRow key={upload.id} upload={upload} />
      ))}
    </>
  )
}
