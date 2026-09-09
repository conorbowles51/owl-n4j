import { useParams } from "react-router-dom"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { WorkspaceRedesignPage } from "./WorkspaceRedesignPage"

export function WorkspacePage() {
  const { id: caseId } = useParams()

  if (!caseId) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return <WorkspaceRedesignPage caseId={caseId} />
}
