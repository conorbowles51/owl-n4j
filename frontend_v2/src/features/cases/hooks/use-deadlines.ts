import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { deadlinesAPI } from "../deadlines-api"

export function useDeadlines(caseId: string | undefined) {
  return useQuery({
    queryKey: ["deadlines", caseId],
    queryFn: () => deadlinesAPI.list(caseId!),
    enabled: !!caseId,
  })
}

export function useCreateDeadline(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string; due_date: string }) =>
      deadlinesAPI.create(caseId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deadlines", caseId] })
      queryClient.invalidateQueries({ queryKey: ["cases"] })
    },
  })
}

export function useUpdateDeadline(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      deadlineId,
      data,
    }: {
      deadlineId: string
      data: { name?: string; due_date?: string }
    }) => deadlinesAPI.update(caseId, deadlineId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deadlines", caseId] })
      queryClient.invalidateQueries({ queryKey: ["cases"] })
    },
  })
}

export function useDeleteDeadline(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (deadlineId: string) =>
      deadlinesAPI.delete(caseId, deadlineId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deadlines", caseId] })
      queryClient.invalidateQueries({ queryKey: ["cases"] })
    },
  })
}
