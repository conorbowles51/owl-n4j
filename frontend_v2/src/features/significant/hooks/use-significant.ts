import { useMemo } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { significantAPI } from "../api"
import type {
  SignificantAdditionSource,
  SignificantManifest,
} from "../types"

export const significantKeys = {
  manifest: (caseId: string) => ["significant", caseId] as const,
}

function refreshScopedProjections(
  queryClient: ReturnType<typeof useQueryClient>,
  caseId: string
) {
  void Promise.all([
    queryClient.invalidateQueries({ queryKey: ["graph", caseId] }),
    queryClient.invalidateQueries({ queryKey: ["timeline", caseId] }),
    queryClient.invalidateQueries({ queryKey: ["map", caseId] }),
  ])
}

export function useSignificantManifest(caseId: string | undefined) {
  const query = useQuery({
    queryKey: significantKeys.manifest(caseId ?? "missing"),
    queryFn: () => significantAPI.getManifest(caseId!),
    enabled: Boolean(caseId),
    staleTime: 10_000,
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
  })
  const entityKeySet = useMemo(
    () => new Set(query.data?.entity_keys ?? []),
    [query.data?.entity_keys]
  )
  return { ...query, entityKeySet }
}

export function useAddSignificantEntities(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      entityKeys,
      source,
      context,
    }: {
      entityKeys: string[]
      source: SignificantAdditionSource
      context?: Record<string, unknown>
    }) => significantAPI.addEntities(caseId, entityKeys, source, context),
    onSuccess: (manifest) => {
      queryClient.setQueryData<SignificantManifest>(
        significantKeys.manifest(caseId),
        manifest
      )
      refreshScopedProjections(queryClient, caseId)
    },
  })
}

export function useRemoveSignificantEntities(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (entityKeys: string[]) =>
      significantAPI.removeEntities(caseId, entityKeys),
    onSuccess: (manifest) => {
      queryClient.setQueryData<SignificantManifest>(
        significantKeys.manifest(caseId),
        manifest
      )
      refreshScopedProjections(queryClient, caseId)
    },
  })
}

export function useClearSignificantEntities(caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => significantAPI.clear(caseId),
    onSuccess: (manifest) => {
      queryClient.setQueryData<SignificantManifest>(
        significantKeys.manifest(caseId),
        manifest
      )
      refreshScopedProjections(queryClient, caseId)
    },
  })
}
