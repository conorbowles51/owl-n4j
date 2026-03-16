import { useQuery } from "@tanstack/react-query"
import { graphAPI } from "../api"

export function useGraphData(caseId: string | undefined, limit?: number, sortBy?: string) {
  return useQuery({
    queryKey: ["graph", caseId, limit, sortBy],
    queryFn: () => graphAPI.getGraph({ case_id: caseId!, limit, sort_by: sortBy }),
    enabled: !!caseId,
  })
}

export function useCommunityOverview(caseId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["graph", "community-overview", caseId],
    queryFn: () => graphAPI.getCommunityOverview(caseId!),
    enabled: !!caseId && enabled,
    staleTime: 5 * 60 * 1000, // 5 min — community structure rarely changes
  })
}

export function useGraphSummary(caseId: string | undefined) {
  return useQuery({
    queryKey: ["graph", "summary", caseId],
    queryFn: () => graphAPI.getSummary(caseId!),
    enabled: !!caseId,
  })
}

export function useEntityTypes(caseId: string | undefined) {
  return useQuery({
    queryKey: ["graph", "entity-types", caseId],
    queryFn: () => graphAPI.getEntityTypes(caseId!),
    enabled: !!caseId,
  })
}
