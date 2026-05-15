import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { caseProfilesAPI } from "../api"
import type {
  CaseProfileCreateInput,
  CaseProfilesListParams,
  CaseProfileUpdateInput,
} from "../types"

export const caseProfilesKeys = {
  all: ["case-profiles"] as const,
  lists: (caseId: string) => [...caseProfilesKeys.all, "list", caseId] as const,
  list: (params: CaseProfilesListParams) => [...caseProfilesKeys.lists(params.caseId), params] as const,
  detail: (profileId: string) => [...caseProfilesKeys.all, "detail", profileId] as const,
  context: (profileId: string) => [...caseProfilesKeys.all, "context", profileId] as const,
}

export function useCaseProfiles(params: CaseProfilesListParams, enabled = true) {
  return useQuery({
    queryKey: caseProfilesKeys.list(params),
    queryFn: () => caseProfilesAPI.list(params),
    enabled: enabled && Boolean(params.caseId),
  })
}

export function useCaseProfile(profileId: string | null | undefined) {
  return useQuery({
    queryKey: caseProfilesKeys.detail(profileId ?? ""),
    queryFn: () => caseProfilesAPI.get(profileId!),
    enabled: Boolean(profileId),
  })
}

export function useCaseProfileContext(profileId: string | null | undefined) {
  return useQuery({
    queryKey: caseProfilesKeys.context(profileId ?? ""),
    queryFn: () => caseProfilesAPI.context(profileId!),
    enabled: Boolean(profileId),
  })
}

export function useCreateCaseProfile(caseId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: Omit<CaseProfileCreateInput, "case_id">) =>
      caseProfilesAPI.create({ ...data, case_id: caseId }),
    onSuccess: (profile) => {
      queryClient.invalidateQueries({ queryKey: caseProfilesKeys.lists(caseId) })
      queryClient.setQueryData(caseProfilesKeys.detail(profile.id), profile)
    },
  })
}

export function useUpdateCaseProfile(caseId: string, profileId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: CaseProfileUpdateInput) => caseProfilesAPI.update(profileId, data),
    onSuccess: (profile) => {
      queryClient.invalidateQueries({ queryKey: caseProfilesKeys.lists(caseId) })
      queryClient.invalidateQueries({ queryKey: caseProfilesKeys.context(profileId) })
      queryClient.setQueryData(caseProfilesKeys.detail(profileId), profile)
    },
  })
}

export function useArchiveCaseProfile(caseId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (profileId: string) => caseProfilesAPI.archive(profileId),
    onSuccess: (profile) => {
      queryClient.invalidateQueries({ queryKey: caseProfilesKeys.lists(caseId) })
      queryClient.invalidateQueries({ queryKey: caseProfilesKeys.context(profile.id) })
      queryClient.setQueryData(caseProfilesKeys.detail(profile.id), profile)
    },
  })
}

export function useRestoreCaseProfile(caseId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (profileId: string) => caseProfilesAPI.restore(profileId),
    onSuccess: (profile) => {
      queryClient.invalidateQueries({ queryKey: caseProfilesKeys.lists(caseId) })
      queryClient.invalidateQueries({ queryKey: caseProfilesKeys.context(profile.id) })
      queryClient.setQueryData(caseProfilesKeys.detail(profile.id), profile)
    },
  })
}

export function useDeleteCaseProfile(caseId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (profileId: string) => caseProfilesAPI.delete(profileId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: caseProfilesKeys.lists(caseId) })
    },
  })
}
