import { create } from "zustand"
import { z } from "zod"
import { evidenceAPI } from "@/features/evidence/api"
import { uploadFolderOrArchive } from "@/features/evidence/resumable-upload-groups"
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
    for (const item of items)
      item.status = "Uploading selection — pause or resume below"
    publish(true)
    const receipt = await uploadFolderOrArchive(caseId, files, {}, "files")
    if (!receipt.file_ids || receipt.file_ids.length !== files.length)
      throw Error(
        "The selection is retained but its registration receipt is incomplete. Check upload activity before retrying."
      )
    const result = answer.parse({
      files: await Promise.all(
        receipt.file_ids.map((id) => evidenceAPI.get(id))
      ),
    })
    if (
      result.files.some((file) => file.case_id !== caseId) ||
      new Set(result.files.map((file) => file.original_filename)).size !==
        files.length
    )
      throw Error(
        "The registration receipt does not match this selection. Check the file list before retrying."
      )
    for (const item of items) {
      const saved = result.files.find(
        (file) => file.original_filename === item.name
      )
      if (!saved)
        throw Error(
          "The registration receipt contains a different file. Check the file list before retrying."
        )
      item.fileId = saved.id
      item.status = "Uploaded — waiting to read"
    }
    changed()
    publish(true)
    for (let index = 0; index < files.length; index++) {
      const item = items[index]
      if (!sameOwner()) {
        for (const pending of items.slice(index)) {
          pending.status = "Stopped"
          pending.error =
            "The signed-in user changed. Uploaded PDFs are retained. Check the file list after signing in."
        }
        break
      }
      try {
        if (!sameOwner())
          throw Error(
            "The signed-in user changed. The uploaded file is retained; processing was not requested."
          )
        item.status = "Starting reading"
        publish(true)
        const preparation = started.parse(
          await evidenceAPI.preparePdfReview(caseId, item.fileId!)
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
  } catch (error) {
    for (const item of items) {
      item.status = "Upload needs attention"
      item.error = `${error instanceof Error ? error.message : "Upload interrupted."} Resume the saved selection below; received files do not need to be sent again.`
    }
    throw error
  } finally {
    publish(false)
    changed()
  }
}
