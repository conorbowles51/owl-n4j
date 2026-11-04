import { useMemo, useState } from "react"
import { ChevronDown, ChevronRight, FileText, Sparkles } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { MarkdownSummary } from "@/components/ui/markdown-summary"
import { useEvidence } from "@/features/evidence/hooks/use-evidence"
import type { EvidenceFile } from "@/types/evidence.types"
import { filesWithSummaries } from "../lib/file-summaries"

const PAGE = 8

/**
 * The case's files with their AI summaries shown inline, newest first, each labelled as AI-made. The count says how
 * many files have a summary out of all files, so a short list is never mistaken for the whole case.
 */
export function CaseFileSummaries({ caseId, onOpen }: { caseId: string; onOpen: (file: EvidenceFile) => void }) {
  const { data: files, isLoading, isError } = useEvidence(caseId)
  const [shown, setShown] = useState(PAGE)
  const [expanded, setExpanded] = useState<string | null>(null)
  const { summarised, total } = useMemo(() => filesWithSummaries(files ?? []), [files])

  if (isLoading) return <div className="flex justify-center py-6"><LoadingSpinner size="sm" /></div>
  if (isError) return <p className="px-4 py-3 text-xs text-muted-foreground">Case files could not be loaded; they are on the Evidence page.</p>
  if (!summarised.length) {
    return (
      <EmptyState
        icon={Sparkles}
        title="No file summaries yet"
        description={`${total} file${total === 1 ? "" : "s"} in this case; none has an AI summary. Summaries are written when a document is processed.`}
        className="py-8"
      />
    )
  }
  return (
    <div>
      <p className="px-4 pt-3 text-[11px] text-muted-foreground">
        {summarised.length} of {total} files have an AI summary. Bank statements read by the financial review are summarised
        as payments, not here.
      </p>
      <div className="divide-y divide-border">
        {summarised.slice(0, shown).map((file) => {
          const open = expanded === file.id
          return (
            <div key={file.id} className="px-4 py-3">
              <div className="flex items-center gap-2">
                <button type="button" aria-label={open ? "Show less" : "Show the full summary"} onClick={() => setExpanded(open ? null : file.id)}>
                  {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
                </button>
                <FileText className="size-4 shrink-0 text-muted-foreground" />
                <button type="button" className="min-w-0 flex-1 truncate text-left text-xs font-semibold hover:underline" onClick={() => onOpen(file)}>
                  {file.original_filename}
                </button>
                <Badge variant="outline" className="text-[9px]"><Sparkles className="mr-1 size-2.5" />AI summary</Badge>
              </div>
              <div className={open ? "mt-2 text-xs" : "mt-2 line-clamp-4 text-xs text-muted-foreground"}>
                <MarkdownSummary content={file.summary as string} />
              </div>
            </div>
          )
        })}
      </div>
      {shown < summarised.length && (
        <div className="px-4 py-2">
          <Button variant="ghost" size="sm" onClick={() => setShown(shown + PAGE)}>
            Show {Math.min(PAGE, summarised.length - shown)} more ({summarised.length - shown} not shown)
          </Button>
        </div>
      )}
    </div>
  )
}
