import { fetchAPI } from "@/lib/api-client"
import type { Case } from "@/types/case.types"
import type { CaseProcessingProfile } from "@/types/evidence.types"

export const casesAPI = {
  list: (viewMode?: string) =>
    fetchAPI<{ cases: Case[]; total: number }>(
      `/api/cases${viewMode ? `?view_mode=${viewMode}` : ""}`
    ).then((r) => r.cases),

  get: (caseId: string) => fetchAPI<Case>(`/api/cases/${caseId}`),

  create: (data: { title: string; description?: string }) =>
    fetchAPI<Case>("/api/cases", { method: "POST", body: data }),

  update: (caseId: string, data: Partial<Pick<Case, "title" | "description">>) =>
    fetchAPI<Case>(`/api/cases/${caseId}`, { method: "PATCH", body: data }),

  getProcessingProfile: (caseId: string) =>
    fetchAPI<CaseProcessingProfile>(`/api/cases/${caseId}/processing-profile`),

  updateProcessingProfile: (
    caseId: string,
    data: {
      source_profile_name: string | null
      context_instructions: string | null
      mandatory_instructions: string[]
      special_entity_types: { name: string; description?: string | null }[]
    }
  ) =>
    fetchAPI<CaseProcessingProfile>(`/api/cases/${caseId}/processing-profile`, {
      method: "PUT",
      body: data,
    }),

  delete: (caseId: string) =>
    fetchAPI<void>(`/api/cases/${caseId}`, { method: "DELETE" }),
}
