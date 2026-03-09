import { Sparkles } from "lucide-react"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { useEvidenceSummary } from "../hooks/use-evidence-detail"

interface FileSummaryPanelProps {
  filename: string
  caseId: string
}

export function FileSummaryPanel({ filename, caseId }: FileSummaryPanelProps) {
  const { data, isLoading } = useEvidenceSummary(filename, caseId)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-8">
        <LoadingSpinner size="sm" />
        <span className="text-xs text-muted-foreground">Loading summary...</span>
      </div>
    )
  }

  if (!data?.has_summary || !data.summary) {
    return (
      <div className="flex flex-col items-center gap-2 py-8">
        <Sparkles className="size-6 text-muted-foreground/40" />
        <p className="text-xs text-muted-foreground">
          No AI summary available. Process the file to generate one.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-md bg-amber-500/5 border border-amber-500/20 p-4">
      <div className="mb-2 flex items-center gap-1.5">
        <Sparkles className="size-3.5 text-amber-500" />
        <span className="text-xs font-medium text-amber-500">AI Summary</span>
      </div>
      <p className="text-sm leading-relaxed text-foreground whitespace-pre-wrap">
        {data.summary}
      </p>
    </div>
  )
}
