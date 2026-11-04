import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { caseMembersAPI } from "@/features/cases/members-api"
import type { CasePermissions } from "@/types/case.types"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { isSuperAdminUser } from "@/features/auth/auth.types"

type Rights = Record<string, Record<string, boolean> | undefined>

// GET /members/me answers {membership_role, permissions:{case:{edit,delete}, collaborators:{invite}, evidence:{upload}}};
// caseMembersAPI maps it (preset "owner" | "editor" | "viewer"). The rights are read from the permissions the server
// grants, so a collaborator with edit rights can edit and a viewer cannot.
function useMyMembership(caseId: string | undefined) {
  return useQuery({
    queryKey: ["case-membership-mapped", caseId],
    queryFn: () => caseMembersAPI.getMyMembership(caseId as string),
    enabled: !!caseId,
    retry: false,
  })
}

export function usePermissions(
  caseId: string | undefined
): CasePermissions {
  const { data: membership } = useMyMembership(caseId)
  const user = useAuthStore((s) => s.user)
  const isSuperAdmin = isSuperAdminUser(user)

  return useMemo(() => {
    const rights = (membership?.permissions ?? {}) as Rights
    const isOwner = membership?.preset === "owner"
    const canEdit = isOwner || !!rights.case?.edit || isSuperAdmin
    return {
      canEdit,
      canDelete: isOwner || !!rights.case?.delete || isSuperAdmin,
      canInvite: isOwner || !!rights.collaborators?.invite || isSuperAdmin,
      canUploadEvidence: isOwner || !!rights.evidence?.upload || isSuperAdmin,
      isOwner,
      isSuperAdmin,
    }
  }, [membership, isSuperAdmin])
}
