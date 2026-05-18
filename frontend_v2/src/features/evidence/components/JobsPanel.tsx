import { useMemo } from "react"
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FileText,
  Loader2,
  Trash2,
  UploadCloud,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { fetchAPI } from "@/lib/api-client"
import { cn } from "@/lib/cn"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { useJobs } from "../hooks/use-jobs"
import { useBackgroundTasks } from "../hooks/use-background-tasks"
import { useJobProgress } from "../hooks/use-job-progress"
import { evidenceAPI } from "../api"
import { useEvidenceStore, type UploadActivity } from "../evidence.store"
import { JobCard } from "./JobCard"
import type { BackgroundTask, EvidenceJob, PipelineStage } from "@/types/evidence.types"

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

const ACTIVE_TASK_STATUSES = new Set(["pending", "running"])
const TERMINAL_TASK_STATUSES = new Set(["completed", "failed", "cancelled"])

function formatDuration(startStr?: string | null, endStr?: string | null): string {
  if (!startStr) return "0s"
  const start = new Date(startStr).getTime()
  const end = endStr ? new Date(endStr).getTime() : Date.now()
  const diffMs = Math.max(0, end - start)
  const seconds = Math.floor(diffMs / 1000)

  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return `${hours}h ${remainingMinutes}m`
}

function getTaskProgress(task: BackgroundTask) {
  const total = Number(task.progress?.total ?? 0)
  const completed = Number(task.progress?.completed ?? 0)
  if (task.status === "completed") return 100
  if (!total || total <= 0) return null
  return Math.min(100, Math.round((completed / total) * 100))
}

function taskTypeLabel(taskType: string) {
  if (taskType === "cellebrite_ingestion") return "Cellebrite ingest"
  if (taskType === "wiretap_processing") return "Wiretap processing"
  return taskType.replaceAll("_", " ")
}

function UploadActivityCard({ activity }: { activity: UploadActivity }) {
  const isActive = activity.status === "running"
  const isFailed = activity.status === "failed"
  const isCompleted = activity.status === "completed"
  const duration = formatDuration(
    activity.createdAt,
    isActive ? undefined : activity.updatedAt
  )

  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-3 transition-colors",
        isFailed && "border-red-500/20",
        isCompleted && "border-green-500/20 opacity-80"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2 text-sm font-medium text-foreground">
          <UploadCloud className="size-3.5 shrink-0 text-amber-500" />
          <span className="truncate">{activity.name}</span>
        </span>
        <Badge
          variant="secondary"
          className={cn(
            "shrink-0 border text-[10px]",
            isFailed
              ? "border-red-500/20 bg-red-500/10 text-red-600"
              : isCompleted
                ? "border-green-500/20 bg-green-500/10 text-green-600"
                : "border-amber-500/20 bg-amber-500/10 text-amber-600"
          )}
        >
          {isActive ? <Loader2 className="mr-1 size-2.5 animate-spin" /> : null}
          {isFailed ? "Failed" : isCompleted ? "Uploaded" : "Uploading"}
        </Badge>
      </div>

      <p className="mt-1 truncate text-[10px] text-muted-foreground">
        {activity.error || activity.message || activity.detail || "Upload in progress"}
      </p>

      <div className="mt-2 flex items-center gap-3 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-1">
          <Clock className="size-2.5" />
          {duration}
        </span>
        {isCompleted ? <CheckCircle2 className="ml-auto size-3 text-green-500" /> : null}
        {isFailed ? <AlertCircle className="ml-auto size-3 text-red-500" /> : null}
      </div>
    </div>
  )
}

function BackgroundTaskCard({
  task,
  onClear,
  clearing,
}: {
  task: BackgroundTask
  onClear: (task: BackgroundTask) => void
  clearing: boolean
}) {
  const isActive = ACTIVE_TASK_STATUSES.has(task.status)
  const isFailed = task.status === "failed" || task.status === "cancelled"
  const isCompleted = task.status === "completed"
  const canClear = TERMINAL_TASK_STATUSES.has(task.status)
  const progress = getTaskProgress(task)
  const duration = formatDuration(
    task.started_at || task.created_at,
    isActive ? undefined : task.completed_at || task.updated_at
  )
  const folderPath =
    typeof task.metadata?.folder_path === "string" ? task.metadata.folder_path : null

  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-3 transition-colors",
        isFailed && "border-red-500/20",
        isCompleted && "border-green-500/20 opacity-80"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2 text-sm font-medium text-foreground">
          <FileText className="size-3.5 shrink-0 text-amber-500" />
          <span className="truncate">{task.task_name}</span>
        </span>
        <Badge
          variant="secondary"
          className={cn(
            "shrink-0 border text-[10px]",
            isFailed
              ? "border-red-500/20 bg-red-500/10 text-red-600"
              : isCompleted
                ? "border-green-500/20 bg-green-500/10 text-green-600"
                : "border-amber-500/20 bg-amber-500/10 text-amber-600"
          )}
        >
          {isActive ? <Loader2 className="mr-1 size-2.5 animate-spin" /> : null}
          {task.status}
        </Badge>
      </div>

      {isActive && progress != null ? (
        <div className="mt-2 flex items-center gap-2">
          <Progress value={progress} className="h-1.5 flex-1" />
          <span className="text-[10px] font-mono text-muted-foreground tabular-nums">
            {progress}%
          </span>
        </div>
      ) : null}

      <p className="mt-1 truncate text-[10px] text-muted-foreground">
        {task.error || folderPath || taskTypeLabel(task.task_type)}
      </p>

      <div className="mt-2 flex items-center gap-3 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-1">
          <Clock className="size-2.5" />
          {duration}
        </span>
        {isCompleted ? <CheckCircle2 className="ml-auto size-3 text-green-500" /> : null}
        {isFailed ? <AlertCircle className="ml-auto size-3 text-red-500" /> : null}
      </div>

      {canClear ? (
        <div className="mt-3 flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-[10px] text-muted-foreground"
            onClick={() => onClear(task)}
            disabled={clearing}
          >
            {clearing ? (
              <Loader2 className="size-3 animate-spin" />
            ) : (
              <Trash2 className="size-3" />
            )}
            Clear
          </Button>
        </div>
      ) : null}
    </div>
  )
}

export function JobsPanel({ caseId }: JobsPanelProps) {
  const queryClient = useQueryClient()
  const hasActiveJobs = useMemo(() => {
    return true // Always poll to detect new jobs
  }, [])

  const { data: jobs, isLoading: jobsLoading } = useJobs(caseId, hasActiveJobs)
  const { data: backgroundTasks, isLoading: tasksLoading } = useBackgroundTasks(caseId, true)
  const uploadActivities = useEvidenceStore((s) => s.uploadActivities)
  const clearTerminalUploadActivities = useEvidenceStore((s) => s.clearTerminalUploadActivities)
  const visibleUploadActivities = useMemo(
    () => uploadActivities.filter((activity) => activity.caseId === caseId),
    [caseId, uploadActivities]
  )

  const retryMutation = useMutation({
    mutationFn: async (fileId: string) => {
      return evidenceAPI.processBackground(caseId, [fileId])
    },
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey: ["evidence-jobs", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-folder-contents", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence-folder-tree", caseId] })
      queryClient.invalidateQueries({ queryKey: ["evidence", caseId] })
      await queryClient.refetchQueries({ queryKey: ["evidence-jobs", caseId], type: "active" })
      toast.success("Retry started")
    },
    onError: (error) => {
      toast.error(error.message || "Failed to retry job")
    },
  })

  const clearJobMutation = useMutation({
    mutationFn: async (jobId: string) => {
      return fetchAPI<{ deleted: number }>(`/api/evidence/engine/jobs/${jobId}?case_id=${caseId}`, {
        method: "DELETE",
      })
    },
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey: ["evidence-jobs", caseId] })
      await queryClient.refetchQueries({ queryKey: ["evidence-jobs", caseId], type: "active" })
    },
    onError: (error) => {
      toast.error(error.message || "Failed to clear job")
    },
  })

  const clearCompletedMutation = useMutation({
    mutationFn: async () => {
      const terminalTaskIds =
        backgroundTasks
          ?.filter((task) => TERMINAL_TASK_STATUSES.has(task.status))
          .map((task) => task.id) ?? []
      const [engineResult] = await Promise.all([
        fetchAPI<{ deleted: number }>(`/api/evidence/engine/jobs?case_id=${caseId}`, {
          method: "DELETE",
        }),
        ...terminalTaskIds.map((taskId) =>
          fetchAPI<{ message: string; task_id: string }>(`/api/background-tasks/${taskId}`, {
            method: "DELETE",
          })
        ),
      ])
      return { deleted: engineResult.deleted + terminalTaskIds.length }
    },
    onSuccess: async (result) => {
      clearTerminalUploadActivities(caseId)
      queryClient.invalidateQueries({ queryKey: ["evidence-jobs", caseId] })
      queryClient.invalidateQueries({ queryKey: ["background-tasks", caseId] })
      await queryClient.refetchQueries({ queryKey: ["evidence-jobs", caseId], type: "active" })
      await queryClient.refetchQueries({ queryKey: ["background-tasks", caseId], type: "active" })
      toast.success(
        result.deleted > 0 ? `Cleared ${result.deleted} terminal job${result.deleted !== 1 ? "s" : ""}` : "No terminal jobs to clear"
      )
    },
    onError: (error) => {
      toast.error(error.message || "Failed to clear completed jobs")
    },
  })

  const clearBackgroundTaskMutation = useMutation({
    mutationFn: async (taskId: string) => {
      return fetchAPI<{ message: string; task_id: string }>(`/api/background-tasks/${taskId}`, {
        method: "DELETE",
      })
    },
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey: ["background-tasks", caseId] })
      await queryClient.refetchQueries({ queryKey: ["background-tasks", caseId], type: "active" })
    },
    onError: (error) => {
      toast.error(error.message || "Failed to clear task")
    },
  })

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
    () =>
      (jobs?.filter((j) => ACTIVE_STATUSES.has(j.status)).length ?? 0) +
      (backgroundTasks?.filter((task) => ACTIVE_TASK_STATUSES.has(task.status)).length ?? 0) +
      visibleUploadActivities.filter((activity) => activity.status === "running").length,
    [backgroundTasks, jobs, visibleUploadActivities]
  )

  const completedJobs = useMemo(
    () =>
      jobs?.filter(
        (j) => j.status === "completed" || j.status === "failed"
      ) ?? [],
    [jobs]
  )

  const terminalBackgroundTasks = useMemo(
    () =>
      backgroundTasks?.filter((task) => TERMINAL_TASK_STATUSES.has(task.status)) ?? [],
    [backgroundTasks]
  )

  const terminalUploadActivities = useMemo(
    () =>
      visibleUploadActivities.filter((activity) => activity.status !== "running"),
    [visibleUploadActivities]
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

  const sortedBackgroundTasks = useMemo(() => {
    if (!backgroundTasks) return []
    return [...backgroundTasks].sort((a, b) => {
      const aActive = ACTIVE_TASK_STATUSES.has(a.status) ? 0 : 1
      const bActive = ACTIVE_TASK_STATUSES.has(b.status) ? 0 : 1
      if (aActive !== bActive) return aActive - bActive
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })
  }, [backgroundTasks])

  const isLoading = jobsLoading || tasksLoading
  const hasActivity =
    visibleUploadActivities.length > 0 ||
    sortedBackgroundTasks.length > 0 ||
    sortedJobs.length > 0

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
        {(completedJobs.length > 0 ||
          terminalBackgroundTasks.length > 0 ||
          terminalUploadActivities.length > 0) && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[10px] text-muted-foreground"
            onClick={() => clearCompletedMutation.mutate()}
            disabled={clearCompletedMutation.isPending}
          >
            Clear Terminal
          </Button>
        )}
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        {isLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner size="sm" />
          </div>
        ) : !hasActivity ? (
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
            {visibleUploadActivities.map((activity) => (
              <UploadActivityCard key={activity.id} activity={activity} />
            ))}
            {sortedBackgroundTasks.map((task) => (
              <BackgroundTaskCard
                key={task.id}
                task={task}
                onClear={(selectedTask) => {
                  clearBackgroundTaskMutation.mutate(selectedTask.id)
                }}
                clearing={
                  clearBackgroundTaskMutation.isPending &&
                  clearBackgroundTaskMutation.variables === task.id
                }
              />
            ))}
            {sortedJobs.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                onRetry={(selectedJob: EvidenceJob) => {
                  if (!selectedJob.evidence_file_id) {
                    toast.error("This failed job is not linked to a retryable evidence file")
                    return
                  }
                  retryMutation.mutate(selectedJob.evidence_file_id)
                }}
                onClear={(selectedJob: EvidenceJob) => {
                  clearJobMutation.mutate(selectedJob.id)
                }}
                retrying={retryMutation.isPending && retryMutation.variables === job.evidence_file_id}
                clearing={clearJobMutation.isPending && clearJobMutation.variables === job.id}
              />
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
