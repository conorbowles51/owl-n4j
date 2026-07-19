import { useQuery } from "@tanstack/react-query"
import { graphAPI } from "../api"
import { useCaseLayer } from "@/features/significant/stores/case-layer.store"

export function useGraphData(caseId: string | undefined) {
  const scope = useCaseLayer(caseId)
  return useQuery({
    queryKey: ["graph", caseId, scope],
    queryFn: () => graphAPI.getGraph({ case_id: caseId!, scope }),
    enabled: !!caseId,
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
