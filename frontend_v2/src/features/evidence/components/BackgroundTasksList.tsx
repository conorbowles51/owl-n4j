import { EmptyState } from "@/components/ui/empty-state"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { Loader2 } from "lucide-react"
import { useBackgroundTasks, useDeleteBackgroundTask } from "../hooks/use-background-tasks"
import { TaskCard } from "./TaskCard"
import { toast } from "sonner"

interface BackgroundTasksListProps {
  caseId?: string
}

export function BackgroundTasksList({ caseId }: BackgroundTasksListProps) {
  const { data: tasks, isLoading } = useBackgroundTasks(caseId, true)
  const deleteMutation = useDeleteBackgroundTask()

  const handleDelete = (taskId: string) => {
    deleteMutation.mutate(taskId, {
      onSuccess: () => toast.success("Task deleted"),
      onError: () => toast.error("Failed to delete task"),
    })
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <LoadingSpinner />
      </div>
    )
  }

  if (!tasks?.length) {
    return (
      <EmptyState
        icon={Loader2}
        title="No background tasks"
        description="Tasks will appear here when you process files"
        className="py-8"
      />
    )
  }

  const activeTasks = tasks.filter((t) => t.status === "running" || t.status === "pending")
  const completedTasks = tasks.filter(
    (t) => t.status === "completed" || t.status === "failed" || t.status === "cancelled"
  )

  return (
    <div className="space-y-4">
      {activeTasks.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold text-foreground">
            Active ({activeTasks.length})
          </h3>
          <div className="space-y-2">
            {activeTasks.map((task) => (
              <TaskCard key={task.id} task={task} onDelete={handleDelete} />
            ))}
          </div>
        </div>
      )}
      {completedTasks.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold text-muted-foreground">
            Recent ({completedTasks.length})
          </h3>
          <div className="space-y-2">
            {completedTasks.map((task) => (
              <TaskCard key={task.id} task={task} onDelete={handleDelete} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
