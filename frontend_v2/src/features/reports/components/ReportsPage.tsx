import { useState } from "react"
import { useParams } from "react-router-dom"
import { FileBarChart, Plus, Trash2, Eye, Download } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { useReports, useDeleteReport, type Report } from "../hooks/use-reports"
import { ReportBuilder } from "./ReportBuilder"
import { ReportViewer } from "./ReportViewer"

export function ReportsPage() {
  const { id: caseId } = useParams()
  const { data: reports = [], isLoading } = useReports(caseId)
  const deleteMutation = useDeleteReport(caseId!)
  const [buildOpen, setBuildOpen] = useState(false)
  const [viewingReport, setViewingReport] = useState<Report | null>(null)

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (viewingReport) {
    return (
      <ReportViewer
        report={viewingReport}
        onBack={() => setViewingReport(null)}
      />
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <FileBarChart className="size-4 text-amber-500" />
        <span className="text-sm font-semibold">Reports</span>
        <div className="flex-1" />
        <Badge variant="slate">{reports.length} reports</Badge>
        <Button variant="primary" size="sm" onClick={() => setBuildOpen(true)}>
          <Plus className="size-3.5" />
          New Report
        </Button>
      </div>

      <div className="flex-1 overflow-auto">
        {reports.length === 0 ? (
          <EmptyState
            icon={FileBarChart}
            title="No reports"
            description="Create a report to summarize your investigation findings"
          />
        ) : (
          <div className="space-y-2 p-4">
            {reports.map((report) => (
              <div
                key={report.id}
                className="group flex items-center gap-3 rounded-lg border border-border p-3 hover:bg-muted/30"
              >
                <FileBarChart className="size-4 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{report.title}</p>
                  {report.description && (
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {report.description}
                    </p>
                  )}
                  <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
                    {report.created_at && (
                      <span>
                        Created {new Date(report.created_at).toLocaleDateString()}
                      </span>
                    )}
                    {report.format && (
                      <Badge variant="outline" className="text-[9px]">
                        {report.format}
                      </Badge>
                    )}
                  </div>
                </div>
                <div className="flex gap-1 opacity-0 transition group-hover:opacity-100">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => setViewingReport(report)}
                  >
                    <Eye className="size-3.5" />
                  </Button>
                  <Button variant="ghost" size="icon-sm">
                    <Download className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => deleteMutation.mutate(report.id)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <ReportBuilder
        open={buildOpen}
        onOpenChange={setBuildOpen}
        caseId={caseId!}
      />
    </div>
  )
}
