import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  caseworkAPI,
  type CaseworkCreateInput,
  type CaseworkListParams,
  type CaseworkUpdateInput,
  type CaseworkLinkTargetType,
  type FindingSignificance,
} from "../casework-api"

export const caseworkKeys = {
  all: (caseId: string | undefined) => ["casework", caseId] as const,
  list: (caseId: string | undefined, params: CaseworkListParams) =>
    ["casework", caseId, "list", params] as const,
  detail: (caseId: string | undefined, entryId: string | undefined) =>
    ["casework", caseId, "detail", entryId] as const,
  options: (
    caseId: string | undefined,
    targetType: CaseworkLinkTargetType,
    query: string,
    targetIds: string[] = [],
  ) => ["casework", caseId, "attachment-options", targetType, query, targetIds] as const,
}

export function useCaseworkEntries(
  caseId: string | undefined,
  params: CaseworkListParams,
) {
  return useQuery({
    queryKey: caseworkKeys.list(caseId, params),
    queryFn: () => caseworkAPI.list(caseId!, params),
    enabled: !!caseId,
    placeholderData: (previous) => previous,
  })
}

export function useCaseworkEntry(
  caseId: string | undefined,
  entryId: string | undefined,
  includeDeleted = false,
) {
  return useQuery({
    queryKey: caseworkKeys.detail(caseId, entryId),
    queryFn: () => caseworkAPI.get(caseId!, entryId!, includeDeleted),
    enabled: !!caseId && !!entryId,
  })
}

function useRefreshCasework(caseId: string) {
  const queryClient = useQueryClient()
  return () => Promise.all([
    queryClient.invalidateQueries({ queryKey: caseworkKeys.all(caseId) }),
    queryClient.invalidateQueries({ queryKey: ["workspace", caseId, "overview"] }),
  ])
}

export function useCreateCaseworkEntry(caseId: string) {
  const refresh = useRefreshCasework(caseId)
  return useMutation({
    mutationFn: (input: CaseworkCreateInput) => caseworkAPI.create(caseId, input),
    onSuccess: refresh,
  })
}

export function useUpdateCaseworkEntry(caseId: string) {
  const refresh = useRefreshCasework(caseId)
  return useMutation({
    mutationFn: ({ entryId, input }: { entryId: string; input: CaseworkUpdateInput }) =>
      caseworkAPI.update(caseId, entryId, input),
    onSuccess: refresh,
  })
}

export function useDeleteCaseworkEntry(caseId: string) {
  const refresh = useRefreshCasework(caseId)
  return useMutation({
    mutationFn: ({ entryId, version }: { entryId: string; version: number }) =>
      caseworkAPI.delete(caseId, entryId, version),
    onSuccess: refresh,
  })
}

export function useRestoreCaseworkEntry(caseId: string) {
  const refresh = useRefreshCasework(caseId)
  return useMutation({
    mutationFn: ({ entryId, version }: { entryId: string; version: number }) =>
      caseworkAPI.restore(caseId, entryId, version),
    onSuccess: refresh,
  })
}

export function useChangeCaseworkLifecycle(caseId: string) {
  const refresh = useRefreshCasework(caseId)
  return useMutation({
    mutationFn: ({
      entryId,
      version,
      state,
      rationale,
    }: {
      entryId: string
      version: number
      state: string
      rationale?: string
    }) => caseworkAPI.changeLifecycle(caseId, entryId, version, state, rationale),
    onSuccess: refresh,
  })
}

export function useChangeCaseworkConfidence(caseId: string) {
  const refresh = useRefreshCasework(caseId)
  return useMutation({
    mutationFn: ({
      entryId,
      version,
      confidence,
      rationale,
    }: {
      entryId: string
      version: number
      confidence: number | null
      rationale?: string
    }) =>
      caseworkAPI.changeConfidence(
        caseId,
        entryId,
        version,
        confidence,
        rationale,
      ),
    onSuccess: refresh,
  })
}

export function useChangeCaseworkSignificance(caseId: string) {
  const refresh = useRefreshCasework(caseId)
  return useMutation({
    mutationFn: ({
      entryId,
      version,
      significance,
    }: {
      entryId: string
      version: number
      significance: FindingSignificance
    }) =>
      caseworkAPI.changeSignificance(caseId, entryId, version, significance),
    onSuccess: refresh,
  })
}

export function useConvertTheory(caseId: string) {
  const refresh = useRefreshCasework(caseId)
  return useMutation({
    mutationFn: ({
      entryId,
      version,
      significance,
      draft,
    }: {
      entryId: string
      version: number
      significance: FindingSignificance
      draft?: { title: string; body: string }
    }) => caseworkAPI.convertToFinding(caseId, entryId, version, significance, draft),
    onSuccess: refresh,
  })
}

export function useAttachmentOptions(
  caseId: string,
  targetType: CaseworkLinkTargetType,
  query: string,
  enabled = true,
  targetIds: string[] = [],
) {
  return useQuery({
    queryKey: caseworkKeys.options(caseId, targetType, query, targetIds),
    queryFn: () =>
      caseworkAPI.attachmentOptions(
        caseId,
        targetType,
        query,
        targetIds.length ? Math.min(50, targetIds.length) : 20,
        targetIds,
      ),
    enabled: enabled && !!caseId && targetType !== "graph_entity",
    staleTime: 15_000,
  })
}

export function useCaseworkAuthors(caseId: string) {
  return useQuery({
    queryKey: ["casework", caseId, "authors"],
    queryFn: () => caseworkAPI.authors(caseId),
    enabled: !!caseId,
    staleTime: 30_000,
  })
}
