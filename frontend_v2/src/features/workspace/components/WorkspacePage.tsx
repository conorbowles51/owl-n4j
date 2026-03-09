import { useParams } from "react-router-dom"
import { ScrollArea } from "@/components/ui/scroll-area"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { CaseContextSection } from "./CaseContextSection"
import { TheoriesSection } from "./TheoriesSection"
import { TasksSection } from "./TasksSection"
import { WitnessMatrixSection } from "./WitnessMatrixSection"
import { InvestigativeNotesSection } from "./InvestigativeNotesSection"
import { DocumentsSection } from "./DocumentsSection"
import { CaseFilesSection } from "./CaseFilesSection"
import { SnapshotsSection } from "./SnapshotsSection"

export function WorkspacePage() {
  const { id: caseId } = useParams()

  if (!caseId) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <ScrollArea className="h-full">
      <div className="mx-auto max-w-4xl">
        <CaseContextSection caseId={caseId} />
        <TheoriesSection caseId={caseId} />
        <TasksSection caseId={caseId} />
        <WitnessMatrixSection caseId={caseId} />
        <InvestigativeNotesSection caseId={caseId} />
        <DocumentsSection caseId={caseId} />
        <CaseFilesSection caseId={caseId} />
        <SnapshotsSection caseId={caseId} />
      </div>
    </ScrollArea>
  )
}
