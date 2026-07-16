import { ExternalLink } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { evidenceAPI } from "@/features/evidence/api"
import type { EvidenceFile } from "@/types/evidence.types"

type SummaryFile = Pick<
  EvidenceFile,
  "id" | "original_filename" | "summary" | "summary_source"
>
type SummaryBadgeVariant = "outline" | "info" | "slate"

function hasSummary(file: SummaryFile) {
  return Boolean(file.summary?.trim())
}

function summarySourceLabel(file: SummaryFile) {
  if (!hasSummary(file)) return "No summary"
  return file.summary_source === "human" ? "Human summary" : "AI summary"
}

function summarySourceVariant(file: SummaryFile): SummaryBadgeVariant {
  if (!hasSummary(file)) return "outline"
  return file.summary_source === "human" ? "info" : "slate"
}

export function openEvidenceFile(file: Pick<EvidenceFile, "id">) {
  window.open(evidenceAPI.getFileUrl(file.id), "_blank", "noopener,noreferrer")
}

export function EvidenceSummaryInline({ file }: { file: SummaryFile }) {
  return (
    <div className="mt-1 space-y-1">
      <Badge variant={summarySourceVariant(file)} className="h-4 px-1.5 text-[10px]">
        {summarySourceLabel(file)}
      </Badge>
      <p className="line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
        {hasSummary(file) ? file.summary : "No summary available"}
      </p>
    </div>
  )
}

export function OpenEvidenceFileButton({ file }: { file: SummaryFile }) {
  const label = file.original_filename || "source file"
  return (
    <Button
      variant="ghost"
      size="sm"
      className="h-7 px-2 text-xs"
      onClick={() => openEvidenceFile(file)}
      aria-label={`Open ${label}`}
    >
      <ExternalLink className="size-3.5" />
      Open
    </Button>
  )
}
