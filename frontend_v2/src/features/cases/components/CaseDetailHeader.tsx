import { useNavigate } from "react-router-dom"
import {
  ExternalLink,
  Layout,
  Upload,
  Users,
  Calendar,
  User,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { RoleBadge } from "./RoleBadge"
import type { Case, CasePermissions } from "@/types/case.types"

interface CaseDetailHeaderProps {
  caseData: Case
  permissions: CasePermissions
  onOpenCollaborators: () => void
}

export function CaseDetailHeader({
  caseData,
  permissions,
  onOpenCollaborators,
}: CaseDetailHeaderProps) {
  const navigate = useNavigate()

  return (
    <div className="border-b border-border px-5 py-4">
      {/* Title row */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-lg font-semibold text-foreground">
              {caseData.title}
            </h2>
            <RoleBadge role={caseData.user_role} />
          </div>
          {caseData.description && (
            <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
              {caseData.description}
            </p>
          )}
        </div>
      </div>

      {/* Meta row */}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        {caseData.owner_name && (
          <span className="flex items-center gap-1">
            <User className="size-3" />
            {caseData.owner_name}
          </span>
        )}
        <span className="flex items-center gap-1">
          <Calendar className="size-3" />
          Created {new Date(caseData.created_at).toLocaleDateString()}
        </span>
        <span className="flex items-center gap-1">
          <Calendar className="size-3" />
          Updated {new Date(caseData.updated_at).toLocaleDateString()}
        </span>
      </div>

      {/* Action buttons */}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          variant="primary"
          size="sm"
          onClick={() => navigate(`/cases/${caseData.id}/graph`)}
        >
          <ExternalLink className="size-3.5" />
          Open Case
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate(`/cases/${caseData.id}/workspace`)}
        >
          <Layout className="size-3.5" />
          Workspace
        </Button>
        {permissions.canUploadEvidence && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(`/cases/${caseData.id}/evidence`)}
          >
            <Upload className="size-3.5" />
            Evidence
          </Button>
        )}
        <Button variant="outline" size="sm" onClick={onOpenCollaborators}>
          <Users className="size-3.5" />
          Collaborators
        </Button>
      </div>
    </div>
  )
}
