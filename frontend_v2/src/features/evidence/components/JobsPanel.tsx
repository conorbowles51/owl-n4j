import { useMemo } from "react"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { useJobs } from "../hooks/use-jobs"
import { useJobProgress } from "../hooks/use-job-progress"
import { JobCard } from "./JobCard"
import type { PipelineStage } from "@/types/evidence.types"

interface JobsPanelProps {
  caseId: string
}

const ACTIVE_STATUSES: Set<PipelineStage> = new Set([
  "pending",
  "extracting_text",
  "chunking",
  "extracting_entities",
  "resolving_entities",
  "resolving_relationships",
  "generating_summaries",
  "writing_graph",
])

export function JobsPanel({ caseId }: JobsPanelProps) {
  const hasActiveJobs = useMemo(() => {
    return true // Always poll to detect new jobs
  }, [])

  const { data: jobs, isLoading } = useJobs(caseId, hasActiveJobs)

  // Extract active job IDs for WebSocket real-time updates
  const activeJobIds = useMemo(
    () => jobs?.filter((j) => ACTIVE_STATUSES.has(j.status)).map((j) => j.id) ?? [],
    [jobs]
  )

  // Connect WebSocket for real-time progress on active jobs
  useJobProgress({
    caseId,
    jobIds: activeJobIds,
  })

  const activeCount = useMemo(
    () => jobs?.filter((j) => ACTIVE_STATUSES.has(j.status)).length ?? 0,
    [jobs]
  )

  const completedJobs = useMemo(
    () =>
      jobs?.filter(
        (j) => j.status === "completed" || j.status === "failed"
      ) ?? [],
    [jobs]
  )

  // Sort: active jobs first, then by most recent
  const sortedJobs = useMemo(() => {
    if (!jobs) return []
    return [...jobs].sort((a, b) => {
      const aActive = ACTIVE_STATUSES.has(a.status) ? 0 : 1
      const bActive = ACTIVE_STATUSES.has(b.status) ? 0 : 1
      if (aActive !== bActive) return aActive - bActive
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })
  }, [jobs])

  return (
    <div className="flex h-full flex-col bg-muted/20">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <div className="flex items-center gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Processing Jobs
          </h3>
          {activeCount > 0 && (
            <Badge variant="info" className="px-1.5 py-0 text-[9px] h-4">
              {activeCount} active
            </Badge>
          )}
        </div>
        {completedJobs.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[10px] text-muted-foreground"
            onClick={() => {
              // TODO: implement clear completed jobs
            }}
          >
            Clear Completed
          </Button>
        )}
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        {isLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner size="sm" />
          </div>
        ) : sortedJobs.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 py-8 text-center">
            <Loader2 className="size-8 text-muted-foreground/30" />
            <p className="text-sm font-medium text-muted-foreground">
              No processing activity
            </p>
            <p className="text-xs text-muted-foreground/70">
              Select files and click Process to begin
            </p>
          </div>
        ) : (
          <div className="space-y-1 p-2">
            {sortedJobs.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
