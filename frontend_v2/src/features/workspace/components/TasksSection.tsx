import { useEffect, useMemo, useState } from "react"
import {
  CalendarClock,
  CheckCircle2,
  CheckSquare,
  Circle,
  Clock,
  Plus,
  Trash2,
  UserRound,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { DeadlinesSection } from "@/features/cases/components/DeadlinesSection"
import { useCaseMembers } from "@/features/cases/hooks/use-case-members"
import { cn } from "@/lib/cn"
import type {
  InvestigationTask,
  TaskPriority,
  TaskStatus,
} from "../api"
import {
  useCreateTask,
  useDeleteTask,
  useUpdateTask,
  useWork,
} from "../hooks/use-workspace"

interface TasksSectionProps {
  caseId: string
  canEdit?: boolean
  initialItemId?: string | null
}

type WorkSurface = "upcoming" | "tasks" | "deadlines"

const PRIORITY_STYLE: Record<TaskPriority, { label: string; className: string }> = {
  urgent: { label: "Urgent", className: "border-red-500/20 bg-red-500/10 text-red-600 dark:text-red-300" },
  high: { label: "High", className: "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300" },
  standard: { label: "Standard", className: "" },
  low: { label: "Low", className: "text-muted-foreground" },
}

const STATUS_ORDER: TaskStatus[] = ["todo", "in_progress", "done"]
const STATUS_META: Record<TaskStatus, { label: string; icon: typeof Circle }> = {
  todo: { label: "To Do", icon: Circle },
  in_progress: { label: "In Progress", icon: Clock },
  done: { label: "Done", icon: CheckCircle2 },
}

function groupByStatus(tasks: InvestigationTask[]) {
  return STATUS_ORDER.reduce<Record<TaskStatus, InvestigationTask[]>>(
    (groups, status) => {
      groups[status] = tasks.filter((task) => task.status === status)
      return groups
    },
    { todo: [], in_progress: [], done: [] },
  )
}

function formatWhen(value: string) {
  return new Date(value).toLocaleString([], {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: value.includes("T") ? "2-digit" : undefined,
    minute: value.includes("T") ? "2-digit" : undefined,
  })
}

export function TasksSection({ caseId, canEdit = true, initialItemId = null }: TasksSectionProps) {
  const [surface, setSurface] = useState<WorkSurface>("upcoming")
  const [statusFilter, setStatusFilter] = useState<TaskStatus | "all">("all")
  const [assigneeFilter, setAssigneeFilter] = useState("all")
  const workQuery = useWork(caseId, {
    taskStatus: statusFilter,
    assigneeUserId: assigneeFilter === "all" ? undefined : assigneeFilter,
  })
  const membersQuery = useCaseMembers(caseId)
  const createMutation = useCreateTask(caseId)
  const updateMutation = useUpdateTask(caseId)
  const deleteMutation = useDeleteTask(caseId)
  const tasks = useMemo(() => workQuery.data?.tasks ?? [], [workQuery.data?.tasks])
  const deadlines = useMemo(
    () => workQuery.data?.deadlines ?? [],
    [workQuery.data?.deadlines],
  )
  const members = membersQuery.data ?? []
  const [renderedAt] = useState(() => Date.now())

  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [priority, setPriority] = useState<TaskPriority>("standard")
  const [assigneeUserId, setAssigneeUserId] = useState("")
  const [dueAt, setDueAt] = useState("")
  const [deadlineId, setDeadlineId] = useState("")
  const [parentTaskId, setParentTaskId] = useState("")

  useEffect(() => {
    if (!initialItemId) return
    if (tasks.some((task) => task.id === initialItemId)) setSurface("tasks")
    else if (deadlines.some((deadline) => deadline.id === initialItemId)) setSurface("deadlines")
  }, [deadlines, initialItemId, tasks])

  const topLevelTasks = tasks.filter((task) => !task.parent_task_id)
  const grouped = groupByStatus(tasks)
  const upcoming = useMemo(() => {
    const taskDates = tasks
      .filter((task) => task.due_at && task.status !== "done")
      .map((task) => ({
        id: `task-${task.id}`,
        type: "Task" as const,
        title: task.title,
        date: task.due_at!,
        detail: task.assignee_name || "Unassigned",
        urgent: task.priority === "urgent",
      }))
    const deadlineDates = deadlines.map((deadline) => ({
      id: `deadline-${deadline.id}`,
      type: "Deadline" as const,
      title: deadline.name,
      date: `${deadline.due_date}T00:00:00`,
      detail: "Canonical case deadline",
      urgent: new Date(`${deadline.due_date}T00:00:00`).getTime() < renderedAt,
    }))
    return [...taskDates, ...deadlineDates]
      .sort((left, right) => new Date(left.date).getTime() - new Date(right.date).getTime())
      .slice(0, 50)
  }, [deadlines, renderedAt, tasks])

  const handleAdd = () => {
    if (!title.trim()) return
    createMutation.mutate(
      {
        title: title.trim(),
        description: description.trim() || null,
        status: "todo",
        priority,
        assignee_user_id: assigneeUserId || null,
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
        deadline_id: deadlineId || null,
        parent_task_id: parentTaskId || null,
        links: [],
      },
      {
        onSuccess: () => {
          setTitle("")
          setDescription("")
          setPriority("standard")
          setAssigneeUserId("")
          setDueAt("")
          setDeadlineId("")
          setParentTaskId("")
        },
      },
    )
  }

  const toggleComplete = (task: InvestigationTask) => {
    updateMutation.mutate({
      taskId: task.id,
      updates: { status: task.status === "done" ? "todo" : "done" },
    })
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <CheckSquare className="size-4 text-blue-500" />
            <h2 className="text-sm font-semibold">Work</h2>
            <Badge variant="slate" className="h-5 px-1.5 text-[10px]">
              {workQuery.data?.task_total ?? tasks.length} tasks
            </Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Assign work to case members and keep operational dates in one place.
          </p>
        </div>
        <div className="flex rounded-lg border border-border bg-muted/20 p-0.5">
          {(["upcoming", "tasks", "deadlines"] as WorkSurface[]).map((value) => (
            <Button
              key={value}
              variant={surface === value ? "secondary" : "ghost"}
              size="sm"
              className="h-7 capitalize"
              onClick={() => setSurface(value)}
            >
              {value}
            </Button>
          ))}
        </div>
      </div>

      {surface === "upcoming" && (
        <section className="rounded-xl border border-border bg-card">
          <div className="flex items-center gap-2 border-b border-border px-4 py-3">
            <CalendarClock className="size-4 text-amber-500" />
            <h3 className="text-xs font-semibold">Upcoming dates</h3>
          </div>
          {workQuery.isLoading ? (
            <div className="h-32 animate-pulse bg-muted/20" />
          ) : upcoming.length === 0 ? (
            <p className="px-4 py-8 text-center text-xs text-muted-foreground">
              No open task dates or case deadlines.
            </p>
          ) : (
            <div className="divide-y divide-border">
              {upcoming.map((item) => (
                <div key={item.id} className="flex items-center gap-3 px-4 py-3">
                  <div className={cn(
                    "size-2 rounded-full",
                    item.urgent ? "bg-red-500" : item.type === "Deadline" ? "bg-amber-500" : "bg-blue-500",
                  )} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-xs font-medium">{item.title}</p>
                      <Badge variant="outline" className="text-[9px]">{item.type}</Badge>
                    </div>
                    <p className="mt-0.5 text-[10px] text-muted-foreground">{item.detail}</p>
                  </div>
                  <time className="text-[10px] font-medium text-muted-foreground">
                    {formatWhen(item.date)}
                  </time>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {surface === "tasks" && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground" htmlFor="task-status-filter">Status</label>
            <select id="task-status-filter" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as TaskStatus | "all")} className="h-8 rounded-md border border-input bg-background px-2 text-xs">
              <option value="all">All statuses</option><option value="todo">To Do</option><option value="in_progress">In Progress</option><option value="done">Done</option>
            </select>
            <label className="ml-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground" htmlFor="task-assignee-filter">Assignee</label>
            <select id="task-assignee-filter" value={assigneeFilter} onChange={(event) => setAssigneeFilter(event.target.value)} className="h-8 rounded-md border border-input bg-background px-2 text-xs">
              <option value="all">All case members</option>
              {members.map((member) => <option key={member.user_id} value={member.user_id}>{member.user_name}</option>)}
            </select>
          </div>

          {canEdit && (
            <section className="space-y-3 rounded-xl border border-border bg-card p-4">
              <div className="flex items-center gap-2"><Plus className="size-3.5 text-blue-500" /><h3 className="text-xs font-semibold">Add task</h3></div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Input aria-label="Task title" placeholder="What needs to be done?" value={title} onChange={(event) => setTitle(event.target.value)} className="sm:col-span-2" />
                <Textarea aria-label="Task description" placeholder="Context or expected outcome" value={description} onChange={(event) => setDescription(event.target.value)} rows={2} className="sm:col-span-2" />
                <label className="space-y-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Priority
                  <select aria-label="Task priority" value={priority} onChange={(event) => setPriority(event.target.value as TaskPriority)} className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-xs font-normal normal-case tracking-normal text-foreground">
                    <option value="low">Low</option><option value="standard">Standard</option><option value="high">High</option><option value="urgent">Urgent</option>
                  </select>
                </label>
                <label className="space-y-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Assignee
                  <select aria-label="Task assignee" value={assigneeUserId} onChange={(event) => setAssigneeUserId(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-xs font-normal normal-case tracking-normal text-foreground">
                    <option value="">Unassigned</option>{members.map((member) => <option key={member.user_id} value={member.user_id}>{member.user_name}</option>)}
                  </select>
                </label>
                <label className="space-y-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Due date and time
                  <Input aria-label="Task due date and time" type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} className="mt-1 font-normal normal-case tracking-normal" />
                </label>
                <label className="space-y-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Linked deadline
                  <select aria-label="Linked deadline" value={deadlineId} onChange={(event) => setDeadlineId(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-xs font-normal normal-case tracking-normal text-foreground">
                    <option value="">No linked deadline</option>{deadlines.map((deadline) => <option key={deadline.id} value={deadline.id}>{deadline.name} · {deadline.due_date}</option>)}
                  </select>
                </label>
                <label className="space-y-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground sm:col-span-2">Parent task
                  <select aria-label="Parent task" value={parentTaskId} onChange={(event) => setParentTaskId(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-xs font-normal normal-case tracking-normal text-foreground">
                    <option value="">Top-level task</option>{topLevelTasks.filter((task) => task.status !== "done").map((task) => <option key={task.id} value={task.id}>{task.title}</option>)}
                  </select>
                </label>
              </div>
              <div className="flex justify-end"><Button size="sm" onClick={handleAdd} disabled={!title.trim() || createMutation.isPending}><Plus className="size-3.5" /> Create task</Button></div>
            </section>
          )}

          {workQuery.isLoading ? (
            <div className="space-y-2">{[1, 2, 3].map((item) => <div key={item} className="h-12 animate-pulse rounded-md bg-muted/30" />)}</div>
          ) : tasks.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border py-10 text-center"><CheckSquare className="mx-auto size-8 text-muted-foreground/30" /><p className="mt-2 text-xs text-muted-foreground">No tasks match these filters.</p></div>
          ) : (
            <div className="space-y-5">
              {STATUS_ORDER.map((status) => {
                const group = grouped[status]
                if (group.length === 0) return null
                const meta = STATUS_META[status]
                const StatusIcon = meta.icon
                return (
                  <section key={status} className="space-y-1.5">
                    <div className="flex items-center gap-1.5"><StatusIcon className="size-3.5 text-muted-foreground" /><h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{meta.label}</h3><span className="text-[10px] text-muted-foreground/60">{group.length}</span></div>
                    {group.map((task) => {
                      const priorityMeta = PRIORITY_STYLE[task.priority]
                      const progress = task.subtask_progress
                      return (
                        <div
                          key={task.id}
                          data-attention-target={task.id === initialItemId ? "true" : undefined}
                          className={cn(
                            "group rounded-lg border border-border bg-card px-3 py-2.5",
                            task.parent_task_id && "ml-5 border-l-2 border-l-blue-500/40",
                            task.id === initialItemId && "border-brand-400 ring-2 ring-brand-100 dark:ring-brand-500/15",
                          )}
                        >
                          <div className="flex items-start gap-2.5">
                            <Checkbox aria-label={`Mark ${task.title} complete`} checked={task.status === "done"} disabled={!canEdit} onCheckedChange={() => toggleComplete(task)} />
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className={cn("text-xs font-medium", task.status === "done" && "text-muted-foreground line-through")}>{task.title}</p>
                                {task.priority !== "standard" && <Badge variant="outline" className={cn("text-[9px]", priorityMeta.className)}>{priorityMeta.label}</Badge>}
                                {task.parent_task_id && <Badge variant="secondary" className="text-[9px]">Subtask</Badge>}
                                {task.needs_migration_review && <Badge variant="outline" className="text-[9px] text-amber-600">Review migration</Badge>}
                              </div>
                              {task.description && <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">{task.description}</p>}
                              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
                                {task.assignee_name && <span className="flex items-center gap-1"><UserRound className="size-3" />{task.assignee_name}</span>}
                                {task.due_at && <span className="flex items-center gap-1"><Clock className="size-3" />{formatWhen(task.due_at)}</span>}
                                {task.deadline_name && <span className="flex items-center gap-1"><CalendarClock className="size-3" />{task.deadline_name}</span>}
                                {progress.total > 0 && <span>{progress.done}/{progress.total} subtasks done</span>}
                              </div>
                            </div>
                            {canEdit && (
                              <div className="flex items-center gap-1">
                                <select aria-label={`Status for ${task.title}`} value={task.status} onChange={(event) => updateMutation.mutate({ taskId: task.id, updates: { status: event.target.value as TaskStatus } })} className="h-7 rounded-md border border-input bg-background px-1.5 text-[10px]">
                                  <option value="todo">To Do</option><option value="in_progress">In Progress</option><option value="done">Done</option>
                                </select>
                                <Button variant="ghost" size="icon-sm" aria-label={`Delete ${task.title}`} onClick={() => deleteMutation.mutate(task.id)}><Trash2 className="size-3" /></Button>
                              </div>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </section>
                )
              })}
            </div>
          )}
        </>
      )}

      {surface === "deadlines" && (
        <section className="rounded-xl border border-border bg-card p-4">
          <div className="mb-2 flex items-center gap-2"><CalendarClock className="size-4 text-amber-500" /><h3 className="text-xs font-semibold">Case deadlines</h3></div>
          <DeadlinesSection caseId={caseId} canEdit={canEdit} />
        </section>
      )}
    </div>
  )
}
