import { fetchAPI } from "@/lib/api-client"

export interface CaseMember {
  user_id: string
  user_name: string
  user_email: string
  preset: "viewer" | "editor" | "owner"
  permissions: Record<string, boolean>
  joined_at?: string
}

export interface MyMembership {
  user_id: string
  preset: string
  permissions: Record<string, boolean>
}

export const caseMembersAPI = {
  list: (caseId: string) =>
    fetchAPI<CaseMember[]>(`/api/cases/${caseId}/members`),

  add: (caseId: string, userId: string, preset: "viewer" | "editor") =>
    fetchAPI<CaseMember>(`/api/cases/${caseId}/members`, {
      method: "POST",
      body: { user_id: userId, preset },
    }),

  update: (caseId: string, userId: string, preset: "viewer" | "editor") =>
    fetchAPI<CaseMember>(`/api/cases/${caseId}/members/${userId}`, {
      method: "PATCH",
      body: { preset },
    }),

  remove: (caseId: string, userId: string) =>
    fetchAPI<void>(`/api/cases/${caseId}/members/${userId}`, {
      method: "DELETE",
    }),

  getMyMembership: (caseId: string) =>
    fetchAPI<MyMembership>(`/api/cases/${caseId}/members/me`),
}
