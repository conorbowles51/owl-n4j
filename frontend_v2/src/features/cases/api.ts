import { fetchAPI } from "@/lib/api-client"
import type { Case } from "@/types/case.types"

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

  delete: (caseId: string) =>
    fetchAPI<void>(`/api/cases/${caseId}`, { method: "DELETE" }),
}
