import { useParams } from "react-router-dom"
import { PageHeader } from "@/components/ui/page-header"
import { useCase } from "../hooks/use-cases"

export function CaseSettingsPage() {
  const { id } = useParams()
  const { data: caseData } = useCase(id)

  return (
    <div className="p-6">
      <PageHeader
        title="Case Settings"
        description={caseData?.name ?? "Loading..."}
      />
      <div className="mt-6 text-sm text-muted-foreground">
        Case settings — member management, metadata editing, version management,
        and danger zone will be implemented here.
      </div>
    </div>
  )
}
