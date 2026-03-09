import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { evidenceAPI } from "../api"

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
    },
  })
}

export function useSyncFilesystem(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => evidenceAPI.syncFilesystem(caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
    },
  })
}

export function useProcessBackground(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      fileIds,
      profile,
      maxWorkers,
      imageProvider,
    }: {
      fileIds: string[]
      profile?: string
      maxWorkers?: number
      imageProvider?: string
    }) => evidenceAPI.processBackground(caseId, fileIds, profile, maxWorkers, imageProvider),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["background-tasks"] })
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
    },
  })
}
