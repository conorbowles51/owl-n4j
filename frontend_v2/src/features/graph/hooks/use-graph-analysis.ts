import { useMutation } from "@tanstack/react-query"
import { graphAPI } from "../api"

export function usePageRank(caseId: string) {
  return useMutation({
    mutationFn: (params: {
      nodeKeys?: string[] | null
      topN?: number
      iterations?: number
      dampingFactor?: number
    }) =>
      graphAPI.getPageRank(
        caseId,
        params.nodeKeys,
        params.topN,
        params.iterations,
        params.dampingFactor
      ),
  })
}

export function useLouvainCommunities(caseId: string) {
  return useMutation({
    mutationFn: (params: {
      nodeKeys?: string[] | null
      resolution?: number
      maxIterations?: number
    }) =>
      graphAPI.getLouvainCommunities(
        caseId,
        params.nodeKeys,
        params.resolution,
        params.maxIterations
      ),
  })
}

export function useBetweennessCentrality(caseId: string) {
  return useMutation({
    mutationFn: (params: {
      nodeKeys?: string[] | null
      topN?: number
      normalized?: boolean
    }) =>
      graphAPI.getBetweennessCentrality(
        caseId,
        params.nodeKeys,
        params.topN,
        params.normalized
      ),
  })
}

export function useShortestPaths(caseId: string) {
  return useMutation({
    mutationFn: (params: { nodeKeys: string[]; maxDepth?: number }) =>
      graphAPI.getShortestPaths(caseId, params.nodeKeys, params.maxDepth),
  })
}

export function useAnalyzeRelationships() {
  return useMutation({
    mutationFn: (params: { nodeKey: string; caseId: string }) =>
      graphAPI.analyzeNodeRelationships(params.nodeKey, params.caseId),
  })
}
