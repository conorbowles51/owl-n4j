import { useMutation, useQueryClient } from "@tanstack/react-query"
import { evidenceAPI } from "../api"
import { useEvidenceStore } from "../evidence.store"

function createActivityId() {
  return globalThis.crypto?.randomUUID?.() ?? `upload-${Date.now()}-${Math.random()}`
}

export function useUploadToFolder(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: {
      files: File[]
      folderId?: string | null
      isFolder?: boolean
      isArchive?: boolean
      replaceExisting?: boolean
    }) =>
      evidenceAPI.upload(caseId, data.files, {
        isFolder: data.isFolder,
        isArchive: data.isArchive,
        replaceExisting: data.replaceExisting,
        folderId: data.folderId || undefined,
      }),
    onMutate: (data) => {
      const id = createActivityId()
      const fileCount = data.files.length
      const firstFile = data.files[0]
      const name = data.isArchive
        ? firstFile?.name || "Cellebrite ZIP upload"
        : data.isFolder
          ? `Folder upload (${fileCount.toLocaleString()} files)`
          : fileCount === 1
            ? firstFile?.name || "File upload"
            : `File upload (${fileCount.toLocaleString()} files)`

      const store = useEvidenceStore.getState()
      store.addUploadActivity({
        id,
        caseId,
        name,
        detail: data.isArchive
          ? data.replaceExisting
            ? "Uploading archive and replacing matching report"
            : "Uploading archive and queuing phone ingest"
          : data.isFolder
            ? "Uploading folder"
            : "Uploading files",
        status: "running",
      })
      store.openSidebarTo("processing")
      return { uploadActivityId: id }
    },
    onSuccess: (result, _variables, context) => {
      if (context?.uploadActivityId) {
        useEvidenceStore.getState().updateUploadActivity(context.uploadActivityId, {
          status: "completed",
          message: result.message || "Upload complete",
        })
      }
      qc.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence-jobs", caseId] })
      qc.invalidateQueries({ queryKey: ["background-tasks", caseId] })
      qc.invalidateQueries({ queryKey: ["background-tasks"] })
    },
    onError: (error, _variables, context) => {
      if (context?.uploadActivityId) {
        useEvidenceStore.getState().updateUploadActivity(context.uploadActivityId, {
          status: "failed",
          error: error.message,
        })
      }
    },
  })
}
