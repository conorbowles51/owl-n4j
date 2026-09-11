import { create } from "zustand"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { evidenceAPI } from "@/features/evidence/api"
import { useAuthStore } from "@/features/auth/hooks/use-auth"

type UploadItem = {
  name: string
  status: string
  fileId?: string
  error?: string
}
type Queue = { running: boolean; items: UploadItem[] }
export const useStatementUploads = create<{ queues: Record<string, Queue> }>(
  () => ({ queues: {} })
)
const answer = z.object({
  files: z.array(
    z.object({
      id: z.string(),
      case_id: z.string(),
      original_filename: z.string(),
    })
  ),
})
const started = z.object({
  job_ids: z.array(z.string()).optional().nullable(),
  message: z.string().optional(),
})

export async function uploadStatementFiles(
  files: File[],
  caseId: string,
  owner: string,
  changed: () => void
) {
  const scope = `${owner}:${caseId}`
  if (!files.length || files.length > 20)
    throw Error("Choose between 1 and 20 PDFs at a time.")
  if (files.some((file) => !file.name.toLowerCase().endsWith(".pdf")))
    throw Error("Choose PDF files only.")
  if (useStatementUploads.getState().queues[scope]?.running) return
  const items: UploadItem[] = files.map((file) => ({
    name: file.name,
    status: "Waiting",
  }))
  const publish = (running: boolean) =>
    useStatementUploads.setState((state) => ({
      queues: {
        ...state.queues,
        [scope]: { running, items: items.map((item) => ({ ...item })) },
      },
    }))
  const sameOwner = () => {
    const user = useAuthStore.getState().user
    return (user?.id || user?.username || "anonymous") === owner
  }
  publish(true)
  try {
    for (let index = 0; index < files.length; index++) {
      const item = items[index]
      if (!sameOwner()) {
        for (const pending of items.slice(index)) {
          pending.status = "Stopped"
          pending.error =
            "The signed-in user changed. Select these files again after signing in."
        }
        break
      }
      try {
        item.status = "Uploading"
        publish(true)
        const body = new FormData()
        body.append("case_id", caseId)
        body.append("files", files[index])
        const result = answer.parse(
          await fetchAPI("/api/evidence/upload", {
            method: "POST",
            body,
            timeout: 120000,
          })
        )
        const file = result.files[0]
        if (
          result.files.length !== 1 ||
          file.case_id !== caseId ||
          file.original_filename !== item.name
        )
          throw Error(
            "The server returned a different file or case. Check the file list before retrying."
          )
        item.fileId = file.id
        changed()
        if (!sameOwner())
          throw Error(
            "The signed-in user changed. The uploaded file is retained; processing was not requested."
          )
        item.status = "Starting reading"
        publish(true)
        const preparation = started.parse(
          await evidenceAPI.preparePdfReview(caseId, file.id)
        )
        if (preparation.job_ids?.length !== 1)
          throw Error(
            preparation.message ||
              "No reading job was returned. Check the file status before retrying."
          )
        item.status = "Reading queued"
      } catch (error) {
        item.status = "Needs attention"
        item.error =
          (error instanceof Error
            ? error.message
            : "Upload could not finish.") +
          " Check the file list before uploading another copy."
      }
      publish(true)
      changed()
    }
  } finally {
    publish(false)
    changed()
  }
}
