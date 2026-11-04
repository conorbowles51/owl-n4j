import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { casesAPI } from "@/features/cases/api"

/** Key and fetcher shared by the hook and the start-up prefetch (route-data.ts). */
export const caseProcessingProfileQuery = (caseId: string | undefined) => ({
  queryKey: ["case-processing-profile", caseId],
  queryFn: () => casesAPI.getProcessingProfile(caseId!),
})

export function useCaseProcessingProfile(caseId: string | undefined, enabled = true) {
  return useQuery({
    ...caseProcessingProfileQuery(caseId),
    enabled: !!caseId && enabled,
  })
}

export function useUpdateCaseProcessingProfile(caseId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: {
      source_profile_name: string | null
      context_instructions: string | null
      mandatory_instructions: string[]
      special_entity_types: { name: string; description?: string | null }[]
    }) => casesAPI.updateProcessingProfile(caseId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["case-processing-profile", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-effective-profile"] })
      queryClient.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-jobs", caseId] })
    },
  })
}
