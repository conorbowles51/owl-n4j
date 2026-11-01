import { useMutation, useQueryClient } from "@tanstack/react-query"
import { evidenceAPI } from "../api"
import { useEvidenceStore } from "../evidence.store"
import type { UploadProgress } from "../upload-progress"

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
      activityId?: string
    }) => {
      // Progress reaches the store at most every 250 ms; the card redraws its words every second (07 4.7).
      let last = 0
      let lastPhase = ""
      const onProgress = (progress: UploadProgress) => {
        const now = Date.now()
        if (!data.activityId) return
        if (progress.phase === lastPhase && now - last < 250) return
        last = now
        lastPhase = progress.phase
        useEvidenceStore.getState().updateUploadActivity(data.activityId, { progress })
      }
      return evidenceAPI.upload(caseId, data.files, {
        isFolder: data.isFolder,
        isArchive: data.isArchive,
        folderId: data.folderId || undefined,
        onProgress,
      })
    },
    onMutate: (data) => {
      const id = createActivityId()
      // The same variables object reaches mutationFn, which reports progress against this activity.
      data.activityId = id
      const fileCount = data.files.length
      const firstFile = data.files[0]
      const name = data.isArchive
        ? firstFile?.name || "Archive upload"
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
          ? "Uploading archive"
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
