import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { casesAPI } from "../api"
import type { CaseListViewMode } from "../api"

export function useCases(viewMode?: CaseListViewMode) {
  return useQuery({
    queryKey: ["cases", viewMode ?? "default"],
    queryFn: () => casesAPI.list(viewMode),
  })
}

export function useCase(caseId: string | undefined) {
  return useQuery({
    queryKey: ["cases", caseId],
    queryFn: () => casesAPI.get(caseId!),
    enabled: !!caseId,
  })
}

export function useCreateCase() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: casesAPI.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cases"] })
    },
  })
}

export function useDeleteCase() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: casesAPI.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cases"] })
    },
  })
}
