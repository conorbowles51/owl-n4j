import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { evidenceAPI } from "../api"

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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
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
