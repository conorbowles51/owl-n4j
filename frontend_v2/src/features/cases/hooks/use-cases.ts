import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { casesAPI } from "../api"
import type { CaseListViewMode } from "../api"
import type { CaseMetadataUpdate } from "@/types/case.types"

export const casesListQuery = (viewMode?: CaseListViewMode, includeArchived = false) => ({
  queryKey: ["cases", viewMode ?? "default", includeArchived],
  queryFn: () => casesAPI.list(viewMode, includeArchived),
})

export const caseQuery = (caseId: string | undefined) => ({
  queryKey: ["cases", caseId],
  queryFn: () => casesAPI.get(caseId!),
})

export function useCases(viewMode?: CaseListViewMode, includeArchived = false) {
  return useQuery(casesListQuery(viewMode, includeArchived))
}

export function useCase(caseId: string | undefined) {
  return useQuery({ ...caseQuery(caseId), enabled: !!caseId })
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
      queryClient.invalidateQueries({ queryKey: ["deleted-cases"] })
    },
  })
}

export function useCaseDeletePreview(caseId: string | undefined) {
  return useQuery({
    queryKey: ["cases", caseId, "delete-preview"],
    queryFn: () => casesAPI.deletePreview(caseId!),
    enabled: !!caseId,
    staleTime: 0,
  })
}

export function useDeletedCases(enabled = true) {
  return useQuery({
    queryKey: ["deleted-cases"],
    queryFn: casesAPI.listDeleted,
    enabled,
    staleTime: 0,
  })
}

export function useRestoreCase() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: casesAPI.restore,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cases"] })
      queryClient.invalidateQueries({ queryKey: ["deleted-cases"] })
    },
  })
}

export function useUpdateCase(caseId: string | undefined) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: CaseMetadataUpdate) => casesAPI.update(caseId!, data),
    onSuccess: (updatedCase) => {
      queryClient.setQueryData(["cases", caseId], updatedCase)
      queryClient.invalidateQueries({ queryKey: ["cases"] })
    },
  })
}

export function useArchiveCase() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: casesAPI.archive,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cases"] })
    },
  })
}

export function useUnarchiveCase() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: casesAPI.unarchive,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cases"] })
    },
  })
}
