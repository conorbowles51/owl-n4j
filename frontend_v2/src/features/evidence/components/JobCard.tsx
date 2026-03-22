import { useMemo } from "react"
import { AlertCircle, CheckCircle2, Clock, Loader2, Hash, Link2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/cn"
import type { EvidenceJob, PipelineStage } from "@/types/evidence.types"

interface JobCardProps {
  job: EvidenceJob
}

const STAGE_LABELS: Record<PipelineStage, string> = {
  pending: "Pending",
  extracting_text: "Extracting Text",
  chunking: "Chunking",
  extracting_entities: "Extracting Entities",
  resolving_entities: "Resolving Entities",
  resolving_relationships: "Resolving Relationships",
  generating_summaries: "Generating Summaries",
  writing_graph: "Writing Graph",
  completed: "Completed",
  failed: "Failed",
}

const STAGE_COLORS: Record<PipelineStage, string> = {
  pending: "bg-slate-500/10 text-slate-500 border-slate-500/20",
  extracting_text: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  chunking: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  extracting_entities: "bg-purple-500/10 text-purple-500 border-purple-500/20",
  resolving_entities: "bg-purple-500/10 text-purple-500 border-purple-500/20",
  resolving_relationships: "bg-indigo-500/10 text-indigo-500 border-indigo-500/20",
  generating_summaries: "bg-amber-500/10 text-amber-500 border-amber-500/20",
  writing_graph: "bg-amber-500/10 text-amber-500 border-amber-500/20",
  completed: "bg-green-500/10 text-green-600 border-green-500/20",
  failed: "bg-red-500/10 text-red-600 border-red-500/20",
}

function formatDuration(startStr: string, endStr?: string): string {
  const start = new Date(startStr).getTime()
  const end = endStr ? new Date(endStr).getTime() : Date.now()
  const diffMs = end - start
  const seconds = Math.floor(diffMs / 1000)

  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return `${hours}h ${remainingMinutes}m`
}

export function JobCard({ job }: JobCardProps) {
  const isActive =
    job.status !== "completed" && job.status !== "failed"
  const isFailed = job.status === "failed"
  const isCompleted = job.status === "completed"

  const duration = useMemo(
    () =>
      formatDuration(
        job.created_at,
        isActive ? undefined : job.updated_at
      ),
    [job.created_at, job.updated_at, isActive]
  )

  const stageLabel = STAGE_LABELS[job.status] ?? job.status
  const stageColor = STAGE_COLORS[job.status] ?? STAGE_COLORS.pending

  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-3 transition-colors",
        isFailed && "border-red-500/20",
        isCompleted && "border-green-500/20 opacity-80"
      )}
    >
      {/* Top row: filename + stage badge */}
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-medium text-foreground">
          {job.file_name}
        </span>
        <Badge
          variant="secondary"
          className={cn("shrink-0 border text-[10px]", stageColor)}
        >
          {isActive && (
            <Loader2 className="mr-1 size-2.5 animate-spin" />
          )}
          {stageLabel}
        </Badge>
      </div>

      {/* Progress bar */}
      {isActive && (
        <div className="mt-2 flex items-center gap-2">
          <Progress value={job.progress} className="h-1.5 flex-1" />
          <span className="text-[10px] font-mono text-muted-foreground tabular-nums">
            {Math.round(job.progress)}%
          </span>
        </div>
      )}

      {/* Bottom row: metadata */}
      <div className="mt-2 flex items-center gap-3 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-1">
          <Clock className="size-2.5" />
          {duration}
        </span>

        {isCompleted && (
          <>
            <span className="flex items-center gap-1">
              <Hash className="size-2.5" />
              {job.entity_count} entities
            </span>
            <span className="flex items-center gap-1">
              <Link2 className="size-2.5" />
              {job.relationship_count} rels
            </span>
            <CheckCircle2 className="ml-auto size-3 text-green-500" />
          </>
        )}

        {isFailed && (
          <AlertCircle className="ml-auto size-3 text-red-500" />
        )}
      </div>

      {/* Error message */}
      {isFailed && job.error_message && (
        <div className="mt-2 rounded-md bg-red-500/5 px-2 py-1.5 text-[11px] text-red-600 dark:text-red-400">
          {job.error_message}
        </div>
      )}
    </div>
  )
}
