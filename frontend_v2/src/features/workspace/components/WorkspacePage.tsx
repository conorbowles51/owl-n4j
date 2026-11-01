import { LoadProgress } from "@/features/financial/components/LoadProgress"
import { useParams } from "react-router-dom"
import { WorkspaceRedesignPage } from "./WorkspaceRedesignPage"

export function WorkspacePage() {
  const { id: caseId } = useParams()

  if (!caseId) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadProgress caseId={null} page="case/workspace" />
      </div>
    )
  }

  return <WorkspaceRedesignPage caseId={caseId} />
}
