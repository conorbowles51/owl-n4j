import { Sparkles } from "lucide-react"
import { MarkdownSummary } from "@/components/ui/markdown-summary"

interface FileSummaryPanelProps {
  summary: string | null
  onOpenFile?: (filename: string) => void
}

export function FileSummaryPanel({ summary, onOpenFile }: FileSummaryPanelProps) {
  if (!summary) {
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
      <MarkdownSummary content={summary} onOpenFile={onOpenFile} />
    </div>
  )
}
