import { useState } from "react"
import { CalendarClock, Camera, FolderOpen } from "lucide-react"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { useCase } from "../hooks/use-cases"
import { useCasePermissions } from "../hooks/use-case-permissions"
import { useCaseManagementStore } from "../case-management.store"
import { useSnapshots } from "../hooks/use-snapshots"
import { useDeadlines } from "../hooks/use-deadlines"
import { CaseDetailHeader } from "./CaseDetailHeader"
import { CollapsibleSection } from "./CollapsibleSection"
import { SnapshotsSection } from "./SnapshotsSection"
import { DeadlinesSection } from "./DeadlinesSection"
import { CollaboratorsDialog } from "./CollaboratorsDialog"

export function CaseDetailPanel() {
  const { selectedCaseId, expandedSections, toggleSection } =
    useCaseManagementStore()
  const { data: caseData, isLoading } = useCase(selectedCaseId ?? undefined)
  const permissions = useCasePermissions(caseData)
  const [collabOpen, setCollabOpen] = useState(false)

  // Counts for section badges
  const { data: snapshots } = useSnapshots()
  const snapshotCount =
    snapshots?.filter((s) => s.case_id === selectedCaseId).length ?? 0
  const { data: deadlines } = useDeadlines(selectedCaseId ?? undefined)
  const deadlineCount = deadlines?.length ?? 0

  if (!selectedCaseId) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState
          icon={FolderOpen}
          title="Select a case"
          description="Choose a case from the sidebar to view details"
        />
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!caseData) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState
          icon={FolderOpen}
          title="Case not found"
          description="This case may have been deleted"
        />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <CaseDetailHeader
        caseData={caseData}
        permissions={permissions}
        onOpenCollaborators={() => setCollabOpen(true)}
      />

      <div className="flex-1 overflow-auto">
        <CollapsibleSection
          title="Deadlines"
          icon={CalendarClock}
          count={deadlineCount}
          isExpanded={expandedSections.has("deadlines")}
          onToggle={() => toggleSection("deadlines")}
        >
          <DeadlinesSection caseId={selectedCaseId} />
        </CollapsibleSection>

        <CollapsibleSection
          title="Snapshots"
          icon={Camera}
          count={snapshotCount}
          isExpanded={expandedSections.has("snapshots")}
          onToggle={() => toggleSection("snapshots")}
        >
          <SnapshotsSection caseId={selectedCaseId} />
        </CollapsibleSection>

      </div>

      <CollaboratorsDialog
        open={collabOpen}
        onOpenChange={setCollabOpen}
        caseId={selectedCaseId}
        canInvite={permissions.canInvite}
      />
    </div>
  )
}
