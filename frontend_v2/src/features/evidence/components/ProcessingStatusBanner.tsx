import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { useBackgroundTasks } from "../hooks/use-background-tasks"
import { useEvidenceStore } from "../evidence.store"

interface ProcessingStatusBannerProps {
  caseId: string
}

export function ProcessingStatusBanner({ caseId }: ProcessingStatusBannerProps) {
  const { data: tasks } = useBackgroundTasks(caseId, true)
  const setActiveTab = useEvidenceStore((s) => s.setActiveTab)

  const activeTasks = tasks?.filter(
    (t) => t.status === "running" || t.status === "pending"
  )

  if (!activeTasks?.length) return null

  const task = activeTasks[0]
  const completed = task.progress?.completed ?? 0
  const total = task.progress?.total ?? 0
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0

  return (
    <div className="flex items-center gap-3 border-b border-border bg-amber-500/5 px-6 py-2">
      <Loader2 className="size-3.5 animate-spin text-amber-500" />
      <span className="text-xs font-medium text-foreground truncate">
        {task.task_name}
      </span>
      <Progress value={percent} className="h-1.5 flex-1 max-w-48" />
      <span className="text-xs tabular-nums text-muted-foreground">
        {completed}/{total}
      </span>
      {activeTasks.length > 1 && (
        <span className="text-xs text-muted-foreground">
          +{activeTasks.length - 1} more
        </span>
      )}
      <Button
        variant="ghost"
        size="sm"
        className="h-6 text-xs"
        onClick={() => setActiveTab("activity")}
      >
        View Activity
      </Button>
    </div>
  )
}
