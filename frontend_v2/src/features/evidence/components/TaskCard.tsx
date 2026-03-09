import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Loader2,
  CheckCircle2,
  AlertCircle,
  Clock,
  Trash2,
  ChevronDown,
  ChevronRight,
  FileText,
} from "lucide-react"
import type { BackgroundTask } from "@/types/evidence.types"

interface TaskCardProps {
  task: BackgroundTask
  onDelete: (taskId: string) => void
}

const STATUS_BADGE: Record<string, "info" | "success" | "danger" | "warning" | "slate"> = {
  running: "info",
  completed: "success",
  failed: "danger",
  pending: "slate",
  cancelled: "warning",
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "running":
      return <Loader2 className="size-4 animate-spin text-blue-400" />
    case "completed":
      return <CheckCircle2 className="size-4 text-emerald-400" />
    case "failed":
      return <AlertCircle className="size-4 text-red-400" />
    default:
      return <Clock className="size-4 text-muted-foreground" />
  }
}

export function TaskCard({ task, onDelete }: TaskCardProps) {
  const [expanded, setExpanded] = useState(task.status === "running")

  const progressPercent =
    task.progress && task.progress.total > 0
      ? Math.round(((task.progress.completed ?? 0) / task.progress.total) * 100)
      : 0

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <div className="mt-0.5">
            <StatusIcon status={task.status} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h4 className="truncate text-sm font-medium text-foreground">
                {task.task_name}
              </h4>
              <Badge variant={STATUS_BADGE[task.status] ?? "slate"} className="text-[10px]">
                {task.status}
              </Badge>
            </div>
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              {task.started_at
                ? new Date(task.started_at).toLocaleString()
                : new Date(task.created_at).toLocaleString()}
              {task.completed_at && ` — ${new Date(task.completed_at).toLocaleString()}`}
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => onDelete(task.id)}
          className="shrink-0"
        >
          <Trash2 className="size-3.5 text-red-400" />
        </Button>
      </div>

      {/* Progress */}
      {(task.status === "running" || task.status === "pending") &&
        task.progress &&
        task.progress.total > 0 && (
          <div className="mt-3">
            <div className="mb-1 flex items-center justify-between text-[10px] text-muted-foreground">
              <span>
                {task.progress.completed ?? 0} / {task.progress.total} files
              </span>
              <span>{progressPercent}%</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-amber-500 transition-all"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        )}

      {/* Error */}
      {task.error && (
        <div className="mt-3 rounded-md bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {task.error}
        </div>
      )}

      {/* File list */}
      {task.files && task.files.length > 0 && (
        <div className="mt-3">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            {expanded ? (
              <ChevronDown className="size-3" />
            ) : (
              <ChevronRight className="size-3" />
            )}
            {task.files.length} file{task.files.length !== 1 ? "s" : ""}
          </button>
          {expanded && (
            <div className="mt-2 space-y-1">
              {task.files.map((file, idx) => (
                <div
                  key={file.file_id ?? idx}
                  className="flex items-center gap-2 rounded border border-border bg-muted/30 px-2.5 py-1.5 text-xs"
                >
                  <FileText className="size-3 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate text-foreground">
                    {file.filename || "Unknown"}
                  </span>
                  <Badge
                    variant={
                      file.status === "completed"
                        ? "success"
                        : file.status === "failed"
                          ? "danger"
                          : file.status === "processing"
                            ? "info"
                            : "slate"
                    }
                    className="text-[10px]"
                  >
                    {file.status || "pending"}
                  </Badge>
                  {file.error && (
                    <span
                      className="max-w-[150px] truncate text-[10px] text-red-400"
                      title={file.error}
                    >
                      {file.error}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
