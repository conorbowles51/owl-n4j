import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { caseMembersAPI } from "../members-api"

export function useCaseMembers(caseId: string | undefined) {
  return useQuery({
    queryKey: ["case-members", caseId],
    queryFn: () => caseMembersAPI.list(caseId!),
    enabled: !!caseId,
  })
}

export function useAddCaseMember(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, preset }: { userId: string; preset: "viewer" | "editor" }) =>
      caseMembersAPI.add(caseId, userId, preset),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["case-members", caseId] })
    },
  })
}

export function useUpdateCaseMember(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, preset }: { userId: string; preset: "viewer" | "editor" }) =>
      caseMembersAPI.update(caseId, userId, preset),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["case-members", caseId] })
    },
  })
}

export function useRemoveCaseMember(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => caseMembersAPI.remove(caseId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["case-members", caseId] })
    },
  })
}
