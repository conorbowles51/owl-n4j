import { Sparkles } from "lucide-react"
import { MarkdownSummary } from "@/components/ui/markdown-summary"

interface FileSummaryPanelProps {
  summary: string | null
  onOpenFile?: (filename: string, page?: number) => void
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

  return <MarkdownSummary content={summary} onOpenFile={onOpenFile} />
}
