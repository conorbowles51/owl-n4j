import { Activity, RefreshCw, XCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"

interface BackgroundTask {
  id: string
  type: string
  status: string
  progress?: number
  started_at: string
  completed_at?: string
  error?: string
  metadata?: Record<string, unknown>
}

export function BackgroundTasksPage() {
  const queryClient = useQueryClient()

  const { data: tasks = [], isLoading, refetch } = useQuery({
    queryKey: ["admin", "tasks"],
    queryFn: () => fetchAPI<BackgroundTask[]>("/api/admin/tasks"),
    refetchInterval: 5000,
  })

  const cancelMutation = useMutation({
    mutationFn: (taskId: string) =>
      fetchAPI<void>(`/api/admin/tasks/${taskId}/cancel`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "tasks"] }),
  })

  const running = tasks.filter((t) => t.status === "running")

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <Activity className="size-4 text-amber-500" />
        <span className="text-sm font-semibold">Background Tasks</span>
        <div className="flex-1" />
        <Badge variant={running.length > 0 ? "amber" : "slate"}>
          {running.length} running
        </Badge>
        <Button variant="ghost" size="sm" onClick={() => refetch()}>
          <RefreshCw className="size-3.5" />
        </Button>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {tasks.length === 0 ? (
          <EmptyState
            icon={Activity}
            title="No background tasks"
            description="Tasks will appear here when processing is running"
          />
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => (
              <div
                key={task.id}
                className="rounded-lg border border-border p-3"
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{task.type}</span>
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
                  <span className="text-[10px] text-muted-foreground">
                    {new Date(task.started_at).toLocaleTimeString()}
                  </span>
                  {task.status === "running" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => cancelMutation.mutate(task.id)}
                    >
                      <XCircle className="size-3.5" />
                      Cancel
                    </Button>
                  )}
                </div>
                {task.progress !== undefined && task.status === "running" && (
                  <Progress value={task.progress} className="mt-2" />
                )}
                {task.error && (
                  <p className="mt-1 text-xs text-red-500">{task.error}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
