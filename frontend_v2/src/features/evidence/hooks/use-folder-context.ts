import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { foldersAPI } from "../folders.api"

export function useFolderProfile(folderId: string | null) {
  return useQuery({
    queryKey: ["evidence-folder-profile", folderId],
    queryFn: () => foldersAPI.getProfile(folderId!),
    enabled: !!folderId,
  })
}

export function useEffectiveProfile(folderId: string | null, caseId: string | undefined) {
  return useQuery({
    queryKey: ["evidence-effective-profile", folderId, caseId],
    queryFn: () => foldersAPI.getEffectiveProfile(folderId!, caseId!),
    enabled: !!folderId && !!caseId,
  })
}

export function useUpdateFolderProfile(caseId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: {
      folderId: string
      context_instructions?: string | null
      profile_overrides?: Record<string, unknown> | null
    }) =>
      foldersAPI.updateProfile(data.folderId, {
        context_instructions: data.context_instructions,
        profile_overrides: data.profile_overrides,
      }),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["evidence-folder-profile", vars.folderId] })
      qc.invalidateQueries({ queryKey: ["evidence-effective-profile"] })
      qc.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
    },
  })
}
