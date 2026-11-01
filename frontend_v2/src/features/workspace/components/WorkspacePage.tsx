import { LoadingWords } from "@/components/ui/loading-spinner"
import { useParams } from "react-router-dom"
import { WorkspaceRedesignPage } from "./WorkspaceRedesignPage"

export function WorkspacePage() {
  const { id: caseId } = useParams()

  if (!caseId) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingWords>Opening the case…</LoadingWords>
      </div>
    )
  }

  return <WorkspaceRedesignPage caseId={caseId} />
}
