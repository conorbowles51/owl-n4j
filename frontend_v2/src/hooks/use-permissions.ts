import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import type { CaseMember, CasePermissions } from "@/types/case.types"
import { useAuthStore } from "@/features/auth/hooks/use-auth"

function useMyMembership(caseId: string | undefined) {
  return useQuery({
    queryKey: ["case-membership", caseId],
    queryFn: () =>
      fetchAPI<CaseMember>(`/api/cases/${caseId}/members/me`),
    enabled: !!caseId,
  })
}

export function usePermissions(
  caseId: string | undefined
): CasePermissions {
  const { data: membership } = useMyMembership(caseId)
  const user = useAuthStore((s) => s.user)
  const isSuperAdmin = user?.role === "admin"

  return useMemo(() => {
    const role = membership?.role
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
  }, [membership?.role, isSuperAdmin])
}
