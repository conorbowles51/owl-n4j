import { useMemo } from "react"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import type { Case, CasePermissions } from "@/types/case.types"

export function useCasePermissions(selectedCase: Case | undefined): CasePermissions {
  const user = useAuthStore((s) => s.user)

  return useMemo(() => {
    if (!selectedCase || !user) {
      return {
        canEdit: false,
        canDelete: false,
        canInvite: false,
        canUploadEvidence: false,
        isOwner: false,
        isSuperAdmin: false,
      }
    }

    const isSuperAdmin = user.role === "super_admin" || user.global_role === "super_admin"
    const isOwner = selectedCase.is_owner
    const role = selectedCase.user_role
    const canEdit = isOwner || role === "editor" || role === "admin_access" || isSuperAdmin
    const canDelete = isOwner || isSuperAdmin
    const canInvite = isOwner || isSuperAdmin
    const canUploadEvidence = canEdit

    return { canEdit, canDelete, canInvite, canUploadEvidence, isOwner, isSuperAdmin }
  }, [selectedCase, user])
}
