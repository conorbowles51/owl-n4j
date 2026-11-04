import { FinancialReportsList } from "@/features/financial/components/FinancialReportsList"
import { Link, useParams } from "react-router-dom"
import { FileBarChart, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { CaseworkReportCard } from "./CaseworkReportCard"

export function ReportsPage() {
  const { id: caseId } = useParams()

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex items-center gap-2 border-b border-border bg-card px-4 py-2">
        <FileBarChart className="size-4 text-amber-500" />
        <span className="font-display text-sm font-semibold">Reports</span>
        <div className="flex-1" />
        {caseId && (
          <Button variant="primary" size="sm" asChild>
            <Link to={`/cases/${caseId}/financial?view=findings`}>
              <Plus className="size-3.5" />
              New financial report
            </Link>
          </Button>
        )}
      </div>

      <div className="flex-1 overflow-auto">
        {caseId && (
          <div className="space-y-4 p-4">
            <FinancialReportsList key={caseId} caseId={caseId} />
            <CaseworkReportCard key={`casework-${caseId}`} caseId={caseId} />
          </div>
        )}
      </div>
    </div>
  )
}
