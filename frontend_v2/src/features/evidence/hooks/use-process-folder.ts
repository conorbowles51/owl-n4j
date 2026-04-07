import { useMutation, useQueryClient } from "@tanstack/react-query"
import { foldersAPI } from "../folders.api"

export function useProcessFolder(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: {
      folderId: string
      recursive?: boolean
      reprocessCompleted?: boolean
    }) =>
      foldersAPI.processFolder(
        data.folderId,
        caseId,
        data.recursive ?? true,
        data.reprocessCompleted ?? false
      ),
    onSuccess: async () => {
      qc.invalidateQueries({ queryKey: ["evidence-jobs", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
      qc.invalidateQueries({ queryKey: ["evidence", caseId] })
      await qc.refetchQueries({ queryKey: ["evidence-jobs", caseId], type: "active" })
    },
  })
}
