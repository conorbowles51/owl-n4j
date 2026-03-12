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

export function useFinancialVolume(caseId: string | undefined) {
  return useQuery({
    queryKey: ["financial", "volume", caseId],
    queryFn: () => financialAPI.getVolume(caseId!),
    enabled: !!caseId,
  })
}

export function useFinancialEntities(caseId: string | undefined) {
  return useQuery({
    queryKey: ["financial", "entities", caseId],
    queryFn: () => financialAPI.getEntities(caseId!),
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

export function useUpdateDetails(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      nodeKey,
      purpose,
      counterpartyDetails,
      notes,
    }: {
      nodeKey: string
      purpose?: string
      counterpartyDetails?: string
      notes?: string
    }) =>
      financialAPI.updateDetails(nodeKey, {
        caseId,
        purpose,
        counterpartyDetails,
        notes,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial", caseId] })
    },
  })
}

export function useUpdateAmount(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      nodeKey,
      newAmount,
      correctionReason,
    }: {
      nodeKey: string
      newAmount: number
      correctionReason: string
    }) =>
      financialAPI.updateAmount(nodeKey, {
        caseId,
        newAmount,
        correctionReason,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial", caseId] })
      queryClient.invalidateQueries({ queryKey: ["financial", "summary", caseId] })
    },
  })
}

export function useSetFromTo(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      nodeKey,
      fromKey,
      fromName,
      toKey,
      toName,
    }: {
      nodeKey: string
      fromKey?: string
      fromName?: string
      toKey?: string
      toName?: string
    }) =>
      financialAPI.setFromTo(nodeKey, {
        caseId,
        fromKey,
        fromName,
        toKey,
        toName,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial", caseId] })
    },
  })
}

export function useBatchSetFromTo(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      nodeKeys,
      fromKey,
      fromName,
      toKey,
      toName,
    }: {
      nodeKeys: string[]
      fromKey?: string
      fromName?: string
      toKey?: string
      toName?: string
    }) =>
      financialAPI.batchSetFromTo(nodeKeys, {
        caseId,
        fromKey,
        fromName,
        toKey,
        toName,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial", caseId] })
    },
  })
}

export function useBulkCorrect(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (corrections: { node_key: string; new_amount: number; correction_reason: string }[]) =>
      financialAPI.bulkCorrect(caseId, corrections),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial", caseId] })
      queryClient.invalidateQueries({ queryKey: ["financial", "summary", caseId] })
    },
  })
}

export function useLinkSubTransaction(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ parentKey, childKey }: { parentKey: string; childKey: string }) =>
      financialAPI.linkSubTransaction(parentKey, childKey, caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial", caseId] })
    },
  })
}

export function useUnlinkSubTransaction(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ childKey }: { childKey: string }) =>
      financialAPI.unlinkSubTransaction(childKey, caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial", caseId] })
    },
  })
}

export function useSubTransactions(
  parentKey: string | null,
  caseId: string | undefined
) {
  return useQuery({
    queryKey: ["financial", "sub-transactions", parentKey, caseId],
    queryFn: () => financialAPI.getSubTransactions(parentKey!, caseId!),
    enabled: !!parentKey && !!caseId,
  })
}
