import { keepPreviousData, useQuery } from "@tanstack/react-query"
import {
  judgementCounts,
  judgementRowMap,
  listJudgements,
  searchJudgements,
  type JudgementFilter,
} from "../lib/judgements"

export const judgementKeys = {
  all: (caseId: string) => ["financial-judgements", caseId] as const,
  list: (caseId: string, filter: JudgementFilter) =>
    ["financial-judgements", caseId, "list", filter] as const,
  search: (caseId: string, filter: JudgementFilter) =>
    ["financial-judgements", caseId, "search", filter] as const,
  rows: (caseId: string) => ["financial-judgements", caseId, "rows"] as const,
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

/** One page of the Judgement calls list, with counts per status, type, strength and maker. */
export function useJudgementSearch(caseId: string, filter: JudgementFilter) {
  return useQuery({
    queryKey: judgementKeys.search(caseId, filter),
    queryFn: () => searchJudgements(caseId, filter),
    placeholderData: keepPreviousData,
    retry: false,
    refetchOnWindowFocus: false,
  })
}

/** The case's calls by ledger payment: one read for the whole ledger. */
export function useJudgementRowMap(caseId: string | undefined) {
  return useQuery({
    queryKey: judgementKeys.rows(caseId || "none"),
    queryFn: () => judgementRowMap(caseId!),
    enabled: !!caseId,
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 60_000,
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
