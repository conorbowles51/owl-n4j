import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query"
import { graphAPI, type LocationCorrectionResult } from "../api"

interface UseLocationCorrectionOptions {
  caseId: string
  nodeKey: string | null | undefined
  sourceView: string
  extraInvalidateKeys?: QueryKey[]
  onApplied?: (result: LocationCorrectionResult) => void
  onUndone?: (result: LocationCorrectionResult) => void
}

export function useLocationCorrection({
  caseId,
  nodeKey,
  sourceView,
  extraInvalidateKeys = [],
  onApplied,
  onUndone,
}: UseLocationCorrectionOptions) {
  const queryClient = useQueryClient()

  const invalidateLocationQueries = async () => {
    if (!nodeKey) return
    const queryKeys: QueryKey[] = [
      ["graph", caseId],
      ["graph", "node", nodeKey, caseId],
      ["graph", "summary", caseId],
      ["graph", "entity-types", caseId],
      ["graph", "recycle-bin", caseId],
      ["timeline", caseId],
      ["map", caseId],
      ["financial", caseId],
      ...extraInvalidateKeys,
    ]
    await Promise.all(queryKeys.map((queryKey) => queryClient.invalidateQueries({ queryKey })))
  }

  const previewMutation = useMutation({
    mutationFn: async (address: string) => {
      if (!nodeKey) throw new Error("No entity selected")
      return graphAPI.geocodeNode(nodeKey, caseId, address, false, sourceView)
    },
  })

  const applyMutation = useMutation({
    mutationFn: async (address: string) => {
      if (!nodeKey) throw new Error("No entity selected")
      return graphAPI.geocodeNode(nodeKey, caseId, address, true, sourceView)
    },
    onSuccess: async (result) => {
      await invalidateLocationQueries()
      onApplied?.(result)
    },
  })

  const undoMutation = useMutation({
    mutationFn: async () => {
      if (!nodeKey) throw new Error("No entity selected")
      return graphAPI.undoLocationCorrection(nodeKey, caseId, sourceView)
    },
    onSuccess: async (result) => {
      await invalidateLocationQueries()
      onUndone?.(result)
    },
  })

  return {
    preview: previewMutation.mutateAsync,
    apply: applyMutation.mutateAsync,
    undo: undoMutation.mutateAsync,
    isPreviewing: previewMutation.isPending,
    isApplying: applyMutation.isPending,
    isUndoing: undoMutation.isPending,
    previewError: previewMutation.error,
    applyError: applyMutation.error,
    undoError: undoMutation.error,
  }
}
