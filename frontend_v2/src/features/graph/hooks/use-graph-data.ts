import { useQuery } from "@tanstack/react-query"
import { graphAPI } from "../api"
import { useCaseLayer } from "@/features/significant/stores/case-layer.store"

export function useGraphData(caseId: string | undefined, opts: { phoneCap?: boolean } = {}) {
  const scope = useCaseLayer(caseId)
  return useQuery({
    queryKey: ["graph", caseId, scope, ...(opts.phoneCap ? ["phone-cap"] : [])],
    queryFn: () => graphAPI.getGraph({ case_id: caseId!, scope, phone_cap: opts.phoneCap }),
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
