import { useMutation } from "@tanstack/react-query"
import { graphAPI } from "../api"
import type { CaseLayer } from "@/features/significant/types"

export function usePageRank(caseId: string) {
  return useMutation({
    mutationFn: (params: {
      nodeKeys?: string[] | null
      topN?: number
      iterations?: number
      dampingFactor?: number
      scope?: CaseLayer
    }) =>
      graphAPI.getPageRank(
        caseId,
        params.nodeKeys,
        params.topN,
        params.iterations,
        params.dampingFactor,
        params.scope
      ),
  })
}

export function useLouvainCommunities(caseId: string) {
  return useMutation({
    mutationFn: (params: {
      nodeKeys?: string[] | null
      resolution?: number
      maxIterations?: number
      scope?: CaseLayer
    }) =>
      graphAPI.getLouvainCommunities(
        caseId,
        params.nodeKeys,
        params.resolution,
        params.maxIterations,
        params.scope
      ),
  })
}

export function useBetweennessCentrality(caseId: string) {
  return useMutation({
    mutationFn: (params: {
      nodeKeys?: string[] | null
      topN?: number
      normalized?: boolean
      scope?: CaseLayer
    }) =>
      graphAPI.getBetweennessCentrality(
        caseId,
        params.nodeKeys,
        params.topN,
        params.normalized,
        params.scope
      ),
  })
}

export function useShortestPaths(caseId: string) {
  return useMutation({
    mutationFn: (params: {
      nodeKeys: string[]
      maxDepth?: number
      scope?: CaseLayer
    }) =>
      graphAPI.getShortestPaths(
        caseId,
        params.nodeKeys,
        params.maxDepth,
        params.scope
      ),
  })
}

export function useAnalyzeRelationships() {
  return useMutation({
    mutationFn: (params: { nodeKey: string; caseId: string }) =>
      graphAPI.analyzeNodeRelationships(params.nodeKey, params.caseId),
  })
}
