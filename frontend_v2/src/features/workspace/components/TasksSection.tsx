import { useState } from "react"
import { CheckSquare, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { workspaceAPI, type InvestigationTask } from "../api"
import { WorkspaceSection } from "./WorkspaceSection"
import { cn } from "@/lib/cn"

interface TasksSectionProps {
  caseId: string
}

export function TasksSection({ caseId }: TasksSectionProps) {
  const queryClient = useQueryClient()
  const [newTask, setNewTask] = useState("")

  const { data: tasks = [] } = useQuery({
    queryKey: ["workspace", caseId, "tasks"],
    queryFn: () => workspaceAPI.getTasks(caseId),
  })

  const createMutation = useMutation({
    mutationFn: (task: Omit<InvestigationTask, "id">) =>
      workspaceAPI.createTask(caseId, task),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", caseId, "tasks"] })
      setNewTask("")
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ taskId, updates }: { taskId: string; updates: Partial<InvestigationTask> }) =>
      workspaceAPI.updateTask(caseId, taskId, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", caseId, "tasks"] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (taskId: string) => workspaceAPI.deleteTask(caseId, taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", caseId, "tasks"] })
    },
  })

  const handleAdd = () => {
    if (!newTask.trim()) return
    createMutation.mutate({ title: newTask, status: "pending" })
  }

  const completedCount = tasks.filter((t) => t.status === "completed").length

  return (
    <WorkspaceSection
      title="Tasks"
      icon={CheckSquare}
      count={tasks.length}
      actions={
        <span className="text-[10px] text-muted-foreground">
          {completedCount}/{tasks.length} done
        </span>
      }
    >
      <div className="space-y-1">
        {tasks.map((task) => {
          const done = task.status === "completed"
          return (
            <div
              key={task.id}
              className="group flex items-center gap-2 rounded-md px-2 py-1 hover:bg-muted/30"
            >
              <Checkbox
                checked={done}
                onCheckedChange={(checked) =>
                  updateMutation.mutate({
                    taskId: task.id,
                    updates: { status: checked ? "completed" : "pending" },
                  })
                }
              />
              <span
                className={cn(
                  "flex-1 text-xs",
                  done && "text-muted-foreground line-through"
                )}
              >
                {task.title}
              </span>
              {task.priority && (
                <Badge
                  variant={task.priority === "high" ? "danger" : "outline"}
                  className="text-[9px]"
                >
                  {task.priority}
                </Badge>
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

      {/* Add task */}
      <div className="mt-2 flex gap-1">
        <Input
          placeholder="Add a task..."
          value={newTask}
          onChange={(e) => setNewTask(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          className="h-7 text-xs"
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={handleAdd}
          disabled={!newTask.trim() || createMutation.isPending}
        >
          <Plus className="size-3" />
        </Button>
      </div>
    </WorkspaceSection>
  )
}
