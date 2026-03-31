import { useState } from "react"
import { CheckSquare, Plus, Trash2, Circle, Clock, CheckCircle2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Checkbox } from "@/components/ui/checkbox"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { cn } from "@/lib/cn"
import { useTasks, useCreateTask, useUpdateTask, useDeleteTask } from "../hooks/use-workspace"
import type { InvestigationTask } from "../api"

interface TasksSectionProps {
  caseId: string
}

const PRIORITY_STYLE: Record<string, { label: string; className: string }> = {
  URGENT: { label: "Urgent", className: "bg-red-500/10 text-red-500 border-red-500/20" },
  HIGH: { label: "High", className: "bg-amber-500/10 text-amber-500 border-amber-500/20" },
  STANDARD: { label: "Standard", className: "" },
}

const STATUS_ORDER = ["PENDING", "IN_PROGRESS", "COMPLETED"] as const
const STATUS_META: Record<string, { label: string; icon: React.ComponentType<{ className?: string }> }> = {
  PENDING: { label: "Pending", icon: Circle },
  IN_PROGRESS: { label: "In Progress", icon: Clock },
  COMPLETED: { label: "Completed", icon: CheckCircle2 },
}

function groupByStatus(tasks: InvestigationTask[]) {
  const groups: Record<string, InvestigationTask[]> = {}
  for (const status of STATUS_ORDER) groups[status] = []
  for (const task of tasks) {
    const s = (task.status ?? "PENDING").toUpperCase()
    const key = STATUS_ORDER.includes(s as (typeof STATUS_ORDER)[number]) ? s : "PENDING"
    groups[key].push(task)
  }
  return groups
}

export function TasksSection({ caseId }: TasksSectionProps) {
  const { data: tasks = [], isLoading } = useTasks(caseId)
  const createMutation = useCreateTask(caseId)
  const updateMutation = useUpdateTask(caseId)
  const deleteMutation = useDeleteTask(caseId)

  const [newTitle, setNewTitle] = useState("")
  const [newPriority, setNewPriority] = useState<string>("STANDARD")

  const handleAdd = () => {
    if (!newTitle.trim()) return
    createMutation.mutate(
      { title: newTitle, priority: newPriority as InvestigationTask["priority"], status: "PENDING" },
      { onSuccess: () => { setNewTitle(""); setNewPriority("STANDARD") } },
    )
  }

  const toggleComplete = (task: InvestigationTask) => {
    const newStatus = task.status?.toUpperCase() === "COMPLETED" ? "PENDING" : "COMPLETED"
    updateMutation.mutate({
      taskId: task.id,
      updates: { ...task, status: newStatus },
    })
  }

  const grouped = groupByStatus(tasks)
  const completedCount = grouped.COMPLETED.length

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CheckSquare className="size-4 text-blue-500" />
          <h2 className="text-sm font-semibold">Tasks</h2>
          <Badge variant="slate" className="h-5 px-1.5 text-[10px]">
            {completedCount}/{tasks.length}
          </Badge>
        </div>
      </div>

      {/* Add task */}
      <div className="flex items-center gap-2">
        <Input
          placeholder="Add a task..."
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          className="h-8 flex-1 text-xs"
        />
        <Select value={newPriority} onValueChange={setNewPriority}>
          <SelectTrigger className="h-8 w-28 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="STANDARD">Standard</SelectItem>
            <SelectItem value="HIGH">High</SelectItem>
            <SelectItem value="URGENT">Urgent</SelectItem>
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          size="sm"
          onClick={handleAdd}
          disabled={!newTitle.trim() || createMutation.isPending}
        >
          <Plus className="size-3" />
        </Button>
      </div>

      {/* Task groups */}
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-10 animate-pulse rounded-md bg-muted/30" />
          ))}
        </div>
      ) : tasks.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border py-8">
          <CheckSquare className="size-8 text-muted-foreground/40" />
          <p className="text-xs text-muted-foreground">No tasks yet</p>
        </div>
      ) : (
        <div className="space-y-4">
          {STATUS_ORDER.map((status) => {
            const group = grouped[status]
            if (group.length === 0) return null
            const meta = STATUS_META[status]
            const StatusIcon = meta.icon

            return (
              <div key={status} className="space-y-1">
                <div className="flex items-center gap-1.5 pb-1">
                  <StatusIcon className="size-3 text-muted-foreground" />
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {meta.label}
                  </span>
                  <span className="text-[10px] text-muted-foreground/60">{group.length}</span>
                </div>
                {group.map((task) => {
                  const done = task.status?.toUpperCase() === "COMPLETED"
                  const priorityStyle = PRIORITY_STYLE[task.priority ?? "STANDARD"] ?? PRIORITY_STYLE.STANDARD

                  return (
                    <div
                      key={task.id}
                      className="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/30"
                    >
                      <Checkbox checked={done} onCheckedChange={() => toggleComplete(task)} />
                      <span
                        className={cn(
                          "flex-1 text-xs",
                          done && "text-muted-foreground line-through",
                        )}
                      >
                        {task.title}
                      </span>
                      {task.due_date && (
                        <span className="text-[10px] text-muted-foreground">
                          {new Date(task.due_date).toLocaleDateString()}
                        </span>
                      )}
                      {task.priority && task.priority !== "STANDARD" && (
                        <Badge variant="outline" className={cn("text-[9px]", priorityStyle.className)}>
                          {priorityStyle.label}
                        </Badge>
                      )}
                      {task.assigned_to && (
                        <span className="max-w-20 truncate text-[10px] text-muted-foreground">
                          {task.assigned_to}
                        </span>
                      )}
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="opacity-0 group-hover:opacity-100"
                        onClick={() => deleteMutation.mutate(task.id)}
                      >
                        <Trash2 className="size-3" />
                      </Button>
                    </div>
                  )
                })}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
