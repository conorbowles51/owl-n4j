import { useMutation, useQueryClient } from "@tanstack/react-query"
import { evidenceAPI } from "../api"

export function useUploadToFolder(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { files: File[]; folderId?: string | null }) =>
      evidenceAPI.upload(caseId, data.files, false, data.folderId || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
    },
  })
}
