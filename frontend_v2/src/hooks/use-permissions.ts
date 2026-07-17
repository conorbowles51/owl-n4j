import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import type { CasePermissions } from "@/types/case.types"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { caseMembersAPI } from "@/features/cases/members-api"

function useMyMembership(caseId: string | undefined) {
  return useQuery({
    queryKey: ["case-membership", caseId],
    queryFn: () => caseMembersAPI.getMyMembership(caseId as string),
    enabled: !!caseId,
  })
}

export function usePermissions(
  caseId: string | undefined
): CasePermissions {
  const { data: membership } = useMyMembership(caseId)
  const user = useAuthStore((s) => s.user)
  const userRole = user?.global_role ?? user?.role
  const isSuperAdmin = userRole === "admin" || userRole === "super_admin"

  return useMemo(() => {
    const role = membership?.role ?? membership?.preset
    const isOwner = role === "owner"
    const canEdit = isOwner || role === "editor" || isSuperAdmin
    return {
      canEdit,
      canDelete: isOwner || isSuperAdmin,
      canInvite: isOwner || isSuperAdmin,
      canUploadEvidence: canEdit,
      isOwner,
      isSuperAdmin,
    }
  }, [membership?.role, membership?.preset, isSuperAdmin])
}
