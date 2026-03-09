import { fetchAPI } from "@/lib/api-client"
import type { Case } from "@/types/case.types"

export const casesAPI = {
  list: (viewMode?: string) =>
    fetchAPI<Case[]>(`/api/cases${viewMode ? `?view_mode=${viewMode}` : ""}`),

  get: (caseId: string) => fetchAPI<Case>(`/api/cases/${caseId}`),

  create: (data: { name: string; description?: string }) =>
    fetchAPI<Case>("/api/cases", { method: "POST", body: data }),

  update: (caseId: string, data: Partial<Case>) =>
    fetchAPI<Case>(`/api/cases/${caseId}`, { method: "PATCH", body: data }),

  delete: (caseId: string) =>
    fetchAPI<void>(`/api/cases/${caseId}`, { method: "DELETE" }),
}
