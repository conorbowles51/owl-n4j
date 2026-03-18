import { fetchAPI } from "@/lib/api-client"
import type { CaseDeadline } from "@/types/case.types"

interface DeadlineListResponse {
  deadlines: CaseDeadline[]
  total: number
}

export const deadlinesAPI = {
  list: (caseId: string) =>
    fetchAPI<DeadlineListResponse>(`/api/cases/${caseId}/deadlines`).then(
      (r) => r.deadlines
    ),

  create: (caseId: string, data: { name: string; due_date: string }) =>
    fetchAPI<CaseDeadline>(`/api/cases/${caseId}/deadlines`, {
      method: "POST",
      body: data,
    }),

  update: (
    caseId: string,
    deadlineId: string,
    data: { name?: string; due_date?: string }
  ) =>
    fetchAPI<CaseDeadline>(`/api/cases/${caseId}/deadlines/${deadlineId}`, {
      method: "PATCH",
      body: data,
    }),

  delete: (caseId: string, deadlineId: string) =>
    fetchAPI<void>(`/api/cases/${caseId}/deadlines/${deadlineId}`, {
      method: "DELETE",
    }),
}
