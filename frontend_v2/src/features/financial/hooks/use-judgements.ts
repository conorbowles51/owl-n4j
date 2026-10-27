import { useQuery } from "@tanstack/react-query"
import { judgementCounts, listJudgements, type JudgementFilter } from "../lib/judgements"

export const judgementKeys = {
  all: (caseId: string) => ["financial-judgements", caseId] as const,
  list: (caseId: string, filter: JudgementFilter) =>
    ["financial-judgements", caseId, "list", filter] as const,
  counts: (caseId: string) => ["financial-judgements", caseId, "counts"] as const,
}

export function useJudgements(caseId: string, filter: JudgementFilter, enabled = true) {
  return useQuery({
    queryKey: judgementKeys.list(caseId, filter),
    queryFn: () => listJudgements(caseId, filter),
    enabled,
    retry: false,
    refetchOnWindowFocus: false,
  })
}

export function useJudgementCounts(caseId: string) {
  return useQuery({
    queryKey: judgementKeys.counts(caseId),
    queryFn: () => judgementCounts(caseId),
    retry: false,
    refetchOnWindowFocus: false,
  })
}
