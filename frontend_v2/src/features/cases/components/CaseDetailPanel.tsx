import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import {
  Building2, CalendarClock, ChevronRight, CircleDot, FileText, FolderOpen,
  Landmark, MapPin, MessageCircle, Smartphone, UserRound, type LucideIcon,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { LoadProgress } from "@/features/financial/components/LoadProgress"
import { graphAPI } from "@/features/graph/api"
import { ApiError } from "@/lib/api-client"
import { getNodeColor, typeAliases } from "@/lib/theme"
import { useCase } from "../hooks/use-cases"
import { useCasePermissions } from "../hooks/use-case-permissions"
import { useCaseManagementStore } from "../case-management.store"
import { CaseDetailHeader } from "./CaseDetailHeader"
import { CollaboratorsDialog } from "./CollaboratorsDialog"

const KEY_ENTITY_LIMIT = 5
const entityKinds: Record<string, { icon: LucideIcon; label: string }> = {
  person: { icon: UserRound, label: "Person" },
  organization: { icon: Building2, label: "Organisation" },
  location: { icon: MapPin, label: "Location" },
  financial: { icon: Landmark, label: "Financial entity" },
  document: { icon: FileText, label: "Document" },
  event: { icon: CalendarClock, label: "Event" },
  communication: { icon: MessageCircle, label: "Communication" },
  digital: { icon: Smartphone, label: "Digital entity" },
}
const deadlineDate = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
})

function EntityIcon({ type }: { type: string }) {
  const category = Object.hasOwn(typeAliases, type) ? typeAliases[type] : type
  const { icon: Icon, label } = Object.hasOwn(entityKinds, category)
    ? entityKinds[category]
    : { icon: CircleDot, label: "Entity" }
  const color = getNodeColor(Object.hasOwn(entityKinds, category) ? category : "document")

  return (
    <span
      className="grid size-7 shrink-0 place-items-center rounded-md"
      style={{ color, backgroundColor: `color-mix(in srgb, ${color} 14%, transparent)` }}
    >
      <Icon aria-hidden="true" className="size-3.5" />
      <span className="sr-only">{label} </span>
    </span>
  )
}

export function CaseDetailPanel() {
  const selectedCaseId = useCaseManagementStore((state) => state.selectedCaseId)
  const caseQuery = useCase(selectedCaseId ?? undefined)
  const caseData = caseQuery.data
  const permissions = useCasePermissions(caseData)
  const [collaboratorsCaseId, setCollaboratorsCaseId] = useState<string | null>(null)
  const keyEntities = useQuery({
    queryKey: ["graph", selectedCaseId, "case-preview"],
    queryFn: async () => {
      const graph = await graphAPI.getGraph({
        case_id: selectedCaseId!,
        limit: KEY_ENTITY_LIMIT,
        sort_by: "degree",
      })
      return graph.nodes.slice(0, KEY_ENTITY_LIMIT)
    },
    enabled: !!selectedCaseId && !caseQuery.isError,
    retry: false,
  })

  if (!selectedCaseId) {
    return (
      <div className="grid h-full place-items-center p-5">
        <EmptyState
          icon={FolderOpen}
          title="Select a case"
          description="Choose a case to see its overview."
        />
      </div>
    )
  }

  if (caseQuery.isLoading) {
    return (
      <div className="grid h-full place-items-center p-5">
        <LoadProgress caseId={selectedCaseId} page="case/details" />
      </div>
    )
  }

  if (caseQuery.isError || !caseData) {
    const missing = caseQuery.error instanceof ApiError && caseQuery.error.status === 404

    return (
      <div className="grid h-full place-items-center p-5">
        <EmptyState
          icon={FolderOpen}
          title={missing ? "Case not found" : "Couldn’t load the case"}
          description={missing ? "Choose another case from the list." : "Try again or choose another case."}
          action={missing ? undefined : (
            <Button type="button" variant="outline" className="h-10" onClick={() => void caseQuery.refetch()}>
              Retry
            </Button>
          )}
        />
      </div>
    )
  }

  const deadline = caseData.next_deadline_date

  return (
    <div className="h-full overflow-auto bg-background">
      <section
        aria-labelledby="case-preview-title"
        className="mx-auto w-full max-w-[34rem] px-5 py-6 sm:px-8 sm:py-12 lg:pt-[clamp(3.5rem,9vh,6rem)]"
      >
        <CaseDetailHeader
          caseData={caseData}
          permissions={permissions}
          onOpenCollaborators={() => setCollaboratorsCaseId(selectedCaseId)}
        />

        {(keyEntities.isLoading || keyEntities.isError || !!keyEntities.data?.length) && (
          <section aria-labelledby="case-preview-entities" className="mt-6 border-t border-border/75 pt-5">
            <h3 id="case-preview-entities" className="text-sm font-semibold text-foreground">
              Key entities
            </h3>
            {keyEntities.isLoading ? (
              <p role="status" className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                <LoadingSpinner size="sm" />
                Loading entities…
              </p>
            ) : keyEntities.isError ? (
              <div className="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
                <span>Couldn’t load entities.</span>
                <Button type="button" variant="ghost" className="h-10" onClick={() => void keyEntities.refetch()}>
                  Retry
                </Button>
              </div>
            ) : (
              <ul className="mt-2 space-y-1">
                {keyEntities.data?.map((entity) => (
                  <li key={entity.key} className="flex min-h-8 items-center gap-2.5 py-0.5 text-sm text-foreground">
                    <EntityIcon type={entity.type} />
                    <span className="min-w-0 [overflow-wrap:anywhere]">{entity.label}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {deadline && (
          <div className="mt-5 border-t border-border/75 pt-2">
            <Link
              to={`/cases/${selectedCaseId}/workspace?view=work`}
              className="group flex min-h-10 items-center gap-2.5 rounded-md py-2 text-xs text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/40"
            >
              <CalendarClock aria-hidden="true" className="size-4 shrink-0" />
              <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">
                <span className="mr-2 font-semibold">Next deadline</span>
                {caseData.next_deadline_name && <>{caseData.next_deadline_name} · </>}
                <time dateTime={deadline}>{deadlineDate.format(new Date(deadline))}</time>
              </span>
              <ChevronRight aria-hidden="true" className="size-3.5 shrink-0" />
            </Link>
          </div>
        )}
      </section>
      <CollaboratorsDialog
        key={selectedCaseId}
        open={collaboratorsCaseId === selectedCaseId}
        onOpenChange={(open) => setCollaboratorsCaseId(open ? selectedCaseId : null)}
        caseId={selectedCaseId}
        canInvite={permissions.canInvite}
      />
    </div>
  )
}
