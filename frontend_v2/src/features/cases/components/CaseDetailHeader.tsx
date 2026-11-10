import { Link } from "react-router-dom"
import { ArrowRight, Files, FolderOpen, Users } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { RoleBadge } from "./RoleBadge"
import type { Case, CasePermissions } from "@/types/case.types"

const caseStatuses = {
  active: { label: "Active", variant: "success" },
  on_hold: { label: "On hold", variant: "warning" },
  closed: { label: "Closed", variant: "slate" },
  archived: { label: "Archived", variant: "slate" },
} as const

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
  const status = caseStatuses[caseData.archived ? "archived" : caseData.status]
  const casePath = `/cases/${caseData.id}`

  return (
    <header>
      <div className="flex items-center gap-2.5 text-xs font-semibold text-muted-foreground">
        <span className="grid size-8 place-items-center rounded-lg bg-primary/10 text-primary">
          <FolderOpen aria-hidden="true" className="size-4" />
        </span>
        Case overview
      </div>
      <h2
        id="case-preview-title"
        className="mt-4 font-display text-3xl leading-[1.1] font-semibold tracking-[-0.045em] text-balance text-foreground [overflow-wrap:anywhere] md:text-4xl"
      >
        {caseData.title}
      </h2>
      <div className="mt-3 flex flex-wrap items-center gap-x-2.5 gap-y-2 text-sm text-muted-foreground">
        <Badge variant={status.variant}>{status.label}</Badge>
        {caseData.owner_name && <span>Owned by {caseData.owner_name}</span>}
        <RoleBadge role={caseData.user_role} />
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-x-2 gap-y-1">
        <Button asChild className="h-10 px-4 motion-safe:active:scale-[0.96]">
          <Link to={casePath}>
            Open case
            <ArrowRight aria-hidden="true" className="size-4" />
          </Link>
        </Button>
        {permissions.canUploadEvidence && (
          <Button asChild variant="ghost" className="h-10">
            <Link to={`${casePath}/evidence`}>
              <Files aria-hidden="true" className="size-3.5" />
              Evidence
            </Link>
          </Button>
        )}
        <Button type="button" variant="ghost" className="h-10" onClick={onOpenCollaborators}>
          <Users aria-hidden="true" className="size-3.5" />
          Collaborators
        </Button>
      </div>
    </header>
  )
}
