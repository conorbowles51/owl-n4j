import { ArrowLeft, Download, Printer } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import type { Report } from "../hooks/use-reports"

interface ReportViewerProps {
  report: Report
  onBack: () => void
}

export function ReportViewer({ report, onBack }: ReportViewerProps) {
  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="size-3.5" />
          Back
        </Button>
        <div className="flex-1">
          <p className="text-sm font-semibold">{report.title}</p>
        </div>
        {report.format && (
          <Badge variant="outline">{report.format.toUpperCase()}</Badge>
        )}
        <Button variant="ghost" size="sm">
          <Printer className="size-3.5" />
          Print
        </Button>
        <Button variant="outline" size="sm">
          <Download className="size-3.5" />
          Export
        </Button>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        <div className="mx-auto max-w-3xl p-6">
          {report.content ? (
            <div
              className="prose prose-sm prose-invert max-w-none"
              dangerouslySetInnerHTML={{ __html: report.content }}
            />
          ) : (
            <div className="py-12 text-center">
              <p className="text-sm text-muted-foreground">
                Report content is being generated...
              </p>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
