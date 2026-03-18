export interface Case {
  id: string
  title: string
  description: string | null
  created_by_user_id: string
  owner_user_id: string
  created_at: string
  updated_at: string
  owner_name: string | null
  user_role: string
  is_owner: boolean
  next_deadline_date: string | null
  next_deadline_name: string | null
}

export interface CaseDeadline {
  id: string
  case_id: string
  name: string
  due_date: string
  created_by_user_id: string | null
  created_at: string
  updated_at: string
}

export interface CaseVersion {
  id: string
  name: string
  created_at: string
}

export interface CaseMember {
  user_id: string
  user_name: string
  user_email: string
  preset: "owner" | "editor" | "viewer"
  permissions: Record<string, boolean>
  joined_at?: string
}

export interface CasePermissions {
  canEdit: boolean
  canDelete: boolean
  canInvite: boolean
  canUploadEvidence: boolean
  isOwner: boolean
  isSuperAdmin: boolean
}
