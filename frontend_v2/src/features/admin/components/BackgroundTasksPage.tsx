import { LoadProgress } from "@/features/financial/components/LoadProgress"
import { Activity, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { EmptyState } from "@/components/ui/empty-state"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { TASKS_SHOWN, taskPercent, type BackgroundTask } from "../admin-rows"

export function BackgroundTasksPage() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin", "tasks"],
    queryFn: () =>
      fetchAPI<{ tasks: BackgroundTask[] }>(`/api/background-tasks?all_owners=true&limit=${TASKS_SHOWN}`),
    refetchInterval: 5000,
  })
  const tasks = data?.tasks ?? []

  const running = tasks.filter((t) => t.status === "running")

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadProgress caseId={null} page="admin/tasks" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex items-center gap-2 border-b border-border bg-card px-4 py-2">
        <Activity className="size-4 text-amber-500" />
        <span className="font-display text-sm font-semibold">Background Tasks</span>
        <div className="flex-1" />
        <Badge variant={running.length > 0 ? "amber" : "slate"}>
          {running.length} running
        </Badge>
        <Button variant="ghost" size="sm" onClick={() => refetch()}>
          <RefreshCw className="size-3.5" />
        </Button>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {isError ? (
          <p role="alert" className="py-8 text-center text-sm text-red-500">
            Background tasks could not be read: {error?.message}
          </p>
        ) : tasks.length === 0 ? (
          <EmptyState
            icon={Activity}
            title="No background tasks"
            description="Tasks will appear here when processing is running"
          />
        ) : (
          <div className="space-y-2">
            {tasks.length >= TASKS_SHOWN && (
              <p className="text-xs text-muted-foreground">Showing the newest {TASKS_SHOWN} tasks; older ones are not listed.</p>
            )}
            {tasks.map((task) => {
              const percent = taskPercent(task.progress)
              return (
              <div
                key={task.id}
                className="rounded-lg border border-border bg-card p-3 shadow-sm"
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{task.task_name || task.task_type}</span>
                  <Badge
                    variant={
                      task.status === "running"
                        ? "amber"
                        : task.status === "completed"
                        ? "success"
                        : task.status === "failed"
                        ? "danger"
                        : "slate"
                    }
                  >
                    {task.status}
                  </Badge>
                  <div className="flex-1" />
                  {task.owner && <span className="text-[10px] text-muted-foreground">{task.owner}</span>}
                  <span className="text-[10px] text-muted-foreground">
                    {new Date(task.started_at ?? task.created_at).toLocaleString()}
                  </span>
                </div>
                {percent !== null && task.status === "running" && (
                  <Progress value={percent} className="mt-2" />
                )}
                {task.error && (
                  <p className="mt-1 text-xs text-red-500">{task.error}</p>
                )}
              </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
