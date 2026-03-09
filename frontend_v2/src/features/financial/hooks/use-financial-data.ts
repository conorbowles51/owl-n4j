import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { financialAPI } from "../api"

export function useTransactions(caseId: string | undefined, params?: {
  startDate?: string
  endDate?: string
  categories?: string[]
}) {
  return useQuery({
    queryKey: ["financial", caseId, params],
    queryFn: () =>
      financialAPI.getTransactions({
        caseId: caseId!,
        startDate: params?.startDate,
        endDate: params?.endDate,
        categories: params?.categories,
      }),
    enabled: !!caseId,
  })
}

export function useFinancialSummary(caseId: string | undefined) {
  return useQuery({
    queryKey: ["financial", "summary", caseId],
    queryFn: () => financialAPI.getSummary(caseId!),
    enabled: !!caseId,
  })
}

export function useFinancialCategories(caseId: string | undefined) {
  return useQuery({
    queryKey: ["financial", "categories", caseId],
    queryFn: () => financialAPI.getCategories(caseId!),
    enabled: !!caseId,
  })
}

export function useCategorize(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ nodeKey, category }: { nodeKey: string; category: string }) =>
      financialAPI.categorize(nodeKey, category, caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial", caseId] })
      queryClient.invalidateQueries({ queryKey: ["financial", "summary", caseId] })
    },
  })
}

export function useBatchCategorize(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ nodeKeys, category }: { nodeKeys: string[]; category: string }) =>
      financialAPI.batchCategorize(nodeKeys, category, caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial", caseId] })
      queryClient.invalidateQueries({ queryKey: ["financial", "summary", caseId] })
    },
  })
}

export function useCreateCategory(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ name, color }: { name: string; color: string }) =>
      financialAPI.createCategory(name, color, caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial", "categories", caseId] })
    },
  })
}
