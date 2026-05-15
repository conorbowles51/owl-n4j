import { fetchAPI } from "@/lib/api-client"
import type {
  CaseProfile,
  CaseProfileContext,
  CaseProfileCreateInput,
  CaseProfilesListParams,
  CaseProfilesListResponse,
  CaseProfileUpdateInput,
} from "./types"

function toQuery(params: CaseProfilesListParams): string {
  const query = new URLSearchParams({ case_id: params.caseId })
  if (params.q) query.set("q", params.q)
  if (params.profileType) query.set("profile_type", params.profileType)
  if (params.includeArchived) query.set("include_archived", "true")
  if (params.linkedGraphNodeKey) query.set("linked_graph_node_key", params.linkedGraphNodeKey)
  if (params.linkedEvidenceFileId) query.set("linked_evidence_file_id", params.linkedEvidenceFileId)
  if (params.limit != null) query.set("limit", String(params.limit))
  if (params.offset != null) query.set("offset", String(params.offset))
  return query.toString()
}

export const caseProfilesAPI = {
  list: (params: CaseProfilesListParams) =>
    fetchAPI<CaseProfilesListResponse>(`/api/case-profiles?${toQuery(params)}`),

  get: (profileId: string) =>
    fetchAPI<CaseProfile>(`/api/case-profiles/${encodeURIComponent(profileId)}`),

  create: (data: CaseProfileCreateInput) =>
    fetchAPI<CaseProfile>("/api/case-profiles", {
      method: "POST",
      body: data,
    }),

  update: (profileId: string, data: CaseProfileUpdateInput) =>
    fetchAPI<CaseProfile>(`/api/case-profiles/${encodeURIComponent(profileId)}`, {
      method: "PATCH",
      body: data,
    }),

  archive: (profileId: string) =>
    fetchAPI<CaseProfile>(`/api/case-profiles/${encodeURIComponent(profileId)}/archive`, {
      method: "POST",
    }),

  restore: (profileId: string) =>
    fetchAPI<CaseProfile>(`/api/case-profiles/${encodeURIComponent(profileId)}/restore`, {
      method: "POST",
    }),

  delete: (profileId: string) =>
    fetchAPI<void>(`/api/case-profiles/${encodeURIComponent(profileId)}`, {
      method: "DELETE",
    }),

  context: (profileId: string) =>
    fetchAPI<CaseProfileContext>(
      `/api/case-profiles/${encodeURIComponent(profileId)}/context`
    ),
}
