export interface Case {
  id: string
  name: string
  description: string
  status: "active" | "archived" | "closed"
  created_at: string
  updated_at: string
  member_count: number
}

export interface CaseVersion {
  id: string
  name: string
  created_at: string
}

export interface CaseMember {
  user_id: string
  username: string
  name: string
  role: "owner" | "editor" | "viewer"
  joined_at: string
}

export interface CasePermissions {
  canEdit: boolean
  canDelete: boolean
  canInvite: boolean
  canUploadEvidence: boolean
  isOwner: boolean
  isSuperAdmin: boolean
}
