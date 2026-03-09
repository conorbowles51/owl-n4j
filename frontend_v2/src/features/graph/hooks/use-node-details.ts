import { useQuery } from "@tanstack/react-query"
import { graphAPI } from "../api"

export function useNodeDetails(nodeKey: string | null, caseId: string | undefined) {
  return useQuery({
    queryKey: ["graph", "node", nodeKey, caseId],
    queryFn: () => graphAPI.getNodeDetails(nodeKey!, caseId!),
    enabled: !!nodeKey && !!caseId,
  })
}
