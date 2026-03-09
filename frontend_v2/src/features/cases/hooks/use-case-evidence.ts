import { useQuery } from "@tanstack/react-query"
import { evidenceAPI } from "@/features/evidence/api"

export function useCaseEvidence(caseId: string | undefined) {
  return useQuery({
    queryKey: ["evidence", caseId],
    queryFn: () => evidenceAPI.list(caseId!),
    enabled: !!caseId,
  })
}

export function useEvidenceLogs(caseId: string | undefined) {
  return useQuery({
    queryKey: ["evidence-logs", caseId],
    queryFn: () => evidenceAPI.logs(caseId!),
    enabled: !!caseId,
    refetchInterval: 5000,
  })
}
