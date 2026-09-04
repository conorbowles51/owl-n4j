import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { dossiersAPI, type DossierCreateInput } from "./api"

export const dossierKeys = {
  all: ["dossiers"] as const,
  lists: (caseId: string) => ["dossiers", "list", caseId] as const,
  list: (params: { caseId: string } & Record<string, unknown>) =>
    ["dossiers", "list", params.caseId, params] as const,
  detail: (id: string) => ["dossiers", "detail", id] as const,
}

export function useDossiers(params: Parameters<typeof dossiersAPI.list>[0]) {
  return useQuery({
    queryKey: dossierKeys.list(params),
    queryFn: () => dossiersAPI.list(params),
    enabled: Boolean(params.caseId),
  })
}
export function useDossier(id?: string | null) {
  return useQuery({
    queryKey: dossierKeys.detail(id ?? ""),
    queryFn: () => dossiersAPI.get(id!),
    enabled: Boolean(id),
  })
}
function useRefresh(caseId: string, id?: string) {
  const client = useQueryClient()
  return () => {
    client.invalidateQueries({ queryKey: dossierKeys.lists(caseId) })
    client.invalidateQueries({ queryKey: ["significant", caseId] })
    client.invalidateQueries({ queryKey: ["workspace", caseId, "overview"] })
    if (id) client.invalidateQueries({ queryKey: dossierKeys.detail(id) })
  }
}
export function useCreateDossier(caseId: string) {
  const refresh = useRefresh(caseId)
  return useMutation({
    mutationFn: (input: Omit<DossierCreateInput, "case_id">) =>
      dossiersAPI.create({ ...input, case_id: caseId }),
    onSuccess: refresh,
  })
}
export function useDossierMutation<T>(
  caseId: string,
  id: string,
  mutation: (input: T) => Promise<unknown>
) {
  const refresh = useRefresh(caseId, id)
  return useMutation({ mutationFn: mutation, onSuccess: refresh })
}
