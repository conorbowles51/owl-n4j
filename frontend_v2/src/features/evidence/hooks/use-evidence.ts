import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { evidenceAPI } from "../api"
import type { UploadResponse } from "../api"

export function useEvidence(caseId: string | undefined) {
  return useQuery({
    queryKey: ["evidence", caseId],
    queryFn: () => evidenceAPI.list(caseId!),
    enabled: !!caseId,
  })
}

export function useUploadEvidence(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (files: File[]) => evidenceAPI.upload(caseId, files),
    onSuccess: (data: UploadResponse) => {
      if (data.files) {
        // Sync upload — files are already stored, refresh the list
        queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
      }
      if (data.task_id || data.task_ids) {
        // Background upload — refresh task list so Activity tab picks it up
        queryClient.invalidateQueries({ queryKey: ["background-tasks"] })
      }
    },
  })
}

export function useProcessEvidence(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      fileIds,
      profile,
    }: {
      fileIds: string[]
      profile?: string
    }) => evidenceAPI.process(caseId, fileIds, profile),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
    },
  })
}
