import { fetchAPI } from "@/lib/api-client"
import type { CaseMember } from "@/types/case.types"

type MemberPreset = CaseMember["preset"]

interface BackendMemberUser {
  id: string
  email: string
  name: string
}

interface BackendMemberResponse {
  case_id: string
  user_id: string
  membership_role: "owner" | "collaborator"
  permissions: Record<string, Record<string, boolean>> | null
  added_by_user_id: string
  created_at: string
  updated_at: string
  user: BackendMemberUser | null
}

interface BackendMemberListResponse {
  members: BackendMemberResponse[]
  total: number
}

function toPreset(member: BackendMemberResponse): MemberPreset {
  if (member.membership_role === "owner") {
    return "owner"
  }

  if (member.permissions?.evidence?.upload) {
    return "editor"
  }

  return "viewer"
}

function mapMember(member: BackendMemberResponse): CaseMember {
  return {
    user_id: member.user_id,
    user_name: member.user?.name ?? "Unknown user",
    user_email: member.user?.email ?? "",
    preset: toPreset(member),
    permissions: member.permissions ?? {},
    joined_at: member.created_at,
  }
}

export const caseMembersAPI = {
  list: (caseId: string) =>
    fetchAPI<BackendMemberListResponse>(`/api/cases/${caseId}/members`).then(
      (response) => response.members.map(mapMember)
    ),

  add: (caseId: string, userId: string, preset: "viewer" | "editor") =>
    fetchAPI<BackendMemberResponse>(`/api/cases/${caseId}/members`, {
      method: "POST",
      body: { user_id: userId, preset },
    }).then(mapMember),

  update: (caseId: string, userId: string, preset: "viewer" | "editor") =>
    fetchAPI<BackendMemberResponse>(`/api/cases/${caseId}/members/${userId}`, {
      method: "PATCH",
      body: { preset },
    }).then(mapMember),

  remove: (caseId: string, userId: string) =>
    fetchAPI<void>(`/api/cases/${caseId}/members/${userId}`, {
      method: "DELETE",
    }),

  getMyMembership: (caseId: string) =>
    fetchAPI<BackendMemberResponse>(`/api/cases/${caseId}/members/me`).then(
      mapMember
    ),
}
