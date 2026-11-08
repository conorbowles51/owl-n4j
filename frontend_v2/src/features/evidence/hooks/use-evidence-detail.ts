import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { evidenceAPI } from "../api"

export function useEvidenceFile(evidenceId: string | null) {
  return useQuery({
    queryKey: ["evidence-file", evidenceId],
    queryFn: () => evidenceAPI.get(evidenceId!),
    enabled: Boolean(evidenceId),
  })
}

export function useEvidenceSummary(filename: string | undefined, caseId: string | undefined) {
  return useQuery({
    queryKey: ["evidence-summary", filename, caseId],
    queryFn: () => evidenceAPI.getSummary(filename!, caseId!),
    enabled: !!filename && !!caseId,
  })
}

export function useVideoFrames(evidenceId: string | undefined) {
  return useQuery({
    queryKey: ["video-frames", evidenceId],
    queryFn: async () => {
      const res = await evidenceAPI.getVideoFrames(evidenceId!)
      return res.frames
    },
    enabled: !!evidenceId,
  })
}

export function useDeleteEvidence(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      evidenceId,
      deleteExclusiveEntities = false,
    }: {
      evidenceId: string
      deleteExclusiveEntities?: boolean
    }) => evidenceAPI.delete(evidenceId, caseId, deleteExclusiveEntities),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-deleted", caseId] })
    },
  })
}

export function useDeletedEvidence(caseId: string, enabled = true) {
  return useQuery({
    queryKey: ["evidence-deleted", caseId],
    queryFn: () => evidenceAPI.listDeleted(caseId),
    enabled: enabled && !!caseId,
    staleTime: 0,
  })
}

export function useRestoreEvidence(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (evidenceId: string) => evidenceAPI.restore(evidenceId, caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-deleted", caseId] })
    },
  })
}

export function useDeletedItems(caseId: string, enabled = true) {
  return useQuery({
    queryKey: ["deleted-items", caseId],
    queryFn: () => evidenceAPI.listDeletedItems(caseId),
    enabled: enabled && !!caseId,
    staleTime: 0,
  })
}

/** Restore or remove for good: either can change any screen of the case, so every query is read again. */
export function useDeletedItemAction(caseId: string, action: "restore" | "purge") {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ kind, id }: { kind: string; id: string }): Promise<unknown> =>
      action === "restore"
        ? evidenceAPI.restoreDeletedItem(caseId, kind, id)
        : evidenceAPI.purgeDeletedItem(caseId, kind, id),
    onSuccess: () => {
      queryClient.invalidateQueries()
    },
  })
}

export function useSyncFilesystem(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => evidenceAPI.syncFilesystem(caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
    },
  })
}
