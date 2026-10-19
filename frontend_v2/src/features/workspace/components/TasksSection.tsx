import { useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { CalendarClock, CheckSquare, Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useCaseMembers } from "@/features/cases/hooks/use-case-members"
import {
  useCreateDeadline,
  useUpdateDeadline,
  useDeleteDeadline,
} from "@/features/cases/hooks/use-deadlines"
import { deadlinesAPI } from "@/features/cases/deadlines-api"
import { cn } from "@/lib/cn"
import {
  workspaceAPI,
  type CaseWorkResponse,
  type InvestigationTask,
  type TaskPriority,
  type TaskStatus,
} from "../api"
import {
  useCreateTask,
  useDeleteTask,
  useUpdateTask,
  useWork,
} from "../hooks/use-workspace"

import { workDateLabel } from "../work-date"

type Deadline = CaseWorkResponse["deadlines"][number]
type Selection =
  | { type: "task"; task?: InvestigationTask }
  | { type: "deadline"; deadline?: Deadline }
interface Props {
  caseId: string
  canEdit?: boolean
  initialItemId?: string | null
}

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "Could not save changes. Try again."
const localDateTime = (value?: string | null) => {
  if (!value) return ""
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)
}

function WorkItemDialog({
  caseId,
  selection,
  canEdit,
  tasks,
  deadlines,
  onClose,
}: {
  caseId: string
  selection: Selection
  canEdit: boolean
  tasks: InvestigationTask[]
  deadlines: Deadline[]
  onClose: () => void
}) {
  const task = selection.type === "task" ? selection.task : undefined
  const deadline =
    selection.type === "deadline" ? selection.deadline : undefined
  const existing = Boolean(task || deadline)
  const members = useCaseMembers(caseId).data ?? []
  const createTask = useCreateTask(caseId)
  const updateTask = useUpdateTask(caseId)
  const createDeadline = useCreateDeadline(caseId)
  const updateDeadline = useUpdateDeadline(caseId)
  const [title, setTitle] = useState(task?.title ?? deadline?.name ?? "")
  const [description, setDescription] = useState(task?.description ?? "")
  const [priority, setPriority] = useState<TaskPriority>(
    task?.priority ?? "standard"
  )
  const [status, setStatus] = useState<TaskStatus>(task?.status ?? "todo")
  const [assignee, setAssignee] = useState(task?.assignee_user_id ?? "")
  const [dueAt, setDueAt] = useState(localDateTime(task?.due_at))
  const [dueDate, setDueDate] = useState(deadline?.due_date ?? "")
  const [deadlineId, setDeadlineId] = useState(task?.deadline_id ?? "")
  const [parentId, setParentId] = useState(task?.parent_task_id ?? "")
  const [error, setError] = useState("")
  const snapshot = JSON.stringify([
    title,
    description,
    priority,
    status,
    assignee,
    dueAt,
    dueDate,
    deadlineId,
    parentId,
  ])
  const [original] = useState(snapshot)
  const dirty = original !== snapshot
  const busy =
    createTask.isPending ||
    updateTask.isPending ||
    createDeadline.isPending ||
    updateDeadline.isPending
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ""
    }
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [dirty])
  const close = () => {
    if (!busy && (!dirty || window.confirm("Discard your unsaved changes?")))
      onClose()
  }
  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    setError("")
    try {
      if (selection.type === "deadline") {
        const data = { name: title.trim(), due_date: dueDate }
        if (deadline)
          await updateDeadline.mutateAsync({ deadlineId: deadline.id, data })
        else await createDeadline.mutateAsync(data)
      } else {
        const data = {
          title: title.trim(),
          description: description.trim() || null,
          priority,
          status,
          assignee_user_id: assignee || null,
          due_at: dueAt ? new Date(dueAt).toISOString() : null,
          deadline_id: deadlineId || null,
          parent_task_id: parentId || null,
        }
        if (task)
          await updateTask.mutateAsync({ taskId: task.id, updates: data })
        else await createTask.mutateAsync({ ...data, links: [] })
      }
      toast.success(`${selection.type === "task" ? "Task" : "Deadline"} saved`)
      onClose()
    } catch (e) {
      setError(errorMessage(e))
    }
  }
  return (
    <Dialog open onOpenChange={(open) => !open && close()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {canEdit ? (existing ? "Edit" : "New") : "View"} {selection.type}
          </DialogTitle>
          <DialogDescription>
            {selection.type === "task"
              ? "Assign work, set an optional due date and link it to a case deadline."
              : "Record a case date. Court and jurisdiction details remain in Case Summary."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={save} className="space-y-3">
          <fieldset disabled={!canEdit || busy} className="space-y-3">
            <label className="block space-y-1 text-xs">
              {selection.type === "task" ? "Task title" : "Deadline name"}
              <Input
                aria-label={
                  selection.type === "task" ? "Task title" : "Deadline name"
                }
                required
                autoFocus
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            {selection.type === "deadline" ? (
              <label className="block space-y-1 text-xs">
                Due date
                <Input
                  aria-label="Deadline due date"
                  required
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                />
              </label>
            ) : (
              <>
                <label className="block space-y-1 text-xs">
                  Description
                  <Textarea
                    aria-label="Task description"
                    rows={3}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </label>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-xs">
                    Priority
                    <select
                      aria-label="Task priority"
                      className="mt-1 h-9 w-full rounded-md border bg-background px-2"
                      value={priority}
                      onChange={(e) =>
                        setPriority(e.target.value as TaskPriority)
                      }
                    >
                      {["low", "standard", "high", "urgent"].map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="text-xs">
                    Status
                    <select
                      aria-label="Task status"
                      className="mt-1 h-9 w-full rounded-md border bg-background px-2"
                      value={status}
                      onChange={(e) => setStatus(e.target.value as TaskStatus)}
                    >
                      <option value="todo">To Do</option>
                      <option value="in_progress">In Progress</option>
                      <option value="done">Done</option>
                    </select>
                  </label>
                </div>
                <label className="block text-xs">
                  Assignee
                  <select
                    aria-label="Task assignee"
                    className="mt-1 h-9 w-full rounded-md border bg-background px-2"
                    value={assignee}
                    onChange={(e) => setAssignee(e.target.value)}
                  >
                    <option value="">Unassigned</option>
                    {assignee &&
                      !members.some((m) => m.user_id === assignee) && (
                        <option value={assignee}>
                          {task?.assignee_name || "Existing assignee"}
                        </option>
                      )}
                    {members.map((m) => (
                      <option key={m.user_id} value={m.user_id}>
                        {m.user_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-xs">
                  Due date and time (optional)
                  <Input
                    aria-label="Task due date and time"
                    type="datetime-local"
                    value={dueAt}
                    onChange={(e) => setDueAt(e.target.value)}
                  />
                </label>
                <label className="block text-xs">
                  Linked deadline
                  <select
                    aria-label="Linked deadline"
                    className="mt-1 h-9 w-full rounded-md border bg-background px-2"
                    value={deadlineId}
                    onChange={(e) => setDeadlineId(e.target.value)}
                  >
                    <option value="">No linked deadline</option>
                    {deadlineId &&
                      !deadlines.some((d) => d.id === deadlineId) && (
                        <option value={deadlineId}>
                          {task?.deadline_name || "Existing deadline"}
                        </option>
                      )}
                    {deadlines.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name} · {d.due_date}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-xs">
                  Parent task
                  <select
                    aria-label="Parent task"
                    className="mt-1 h-9 w-full rounded-md border bg-background px-2"
                    value={parentId}
                    onChange={(e) => setParentId(e.target.value)}
                  >
                    <option value="">Top-level task</option>
                    {parentId &&
                      !tasks.some(
                        (t) =>
                          t.id === parentId &&
                          !t.parent_task_id &&
                          t.status !== "done"
                      ) && (
                        <option value={parentId}>Existing parent task</option>
                      )}
                    {tasks
                      .filter(
                        (t) =>
                          t.id !== task?.id &&
                          !t.parent_task_id &&
                          t.status !== "done"
                      )
                      .map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.title}
                        </option>
                      ))}
                  </select>
                </label>
              </>
            )}
          </fieldset>
          {error && (
            <p role="alert" className="text-xs text-destructive">
              {error} Your entries are still here.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={close}
            >
              {canEdit ? "Cancel" : "Close"}
            </Button>
            {canEdit && (
              <Button
                type="submit"
                disabled={
                  busy ||
                  !title.trim() ||
                  (selection.type === "deadline" && !dueDate)
                }
              >
                {busy
                  ? "Saving…"
                  : existing
                    ? "Save changes"
                    : `Create ${selection.type}`}
              </Button>
            )}
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function TasksSection({
  caseId,
  canEdit = true,
  initialItemId = null,
}: Props) {
  const [typeFilter, setTypeFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState<TaskStatus | "all">("all")
  const [assigneeFilter, setAssigneeFilter] = useState("all")
  const [adding, setAdding] = useState(false)
  const [selection, setSelection] = useState<Selection | null>(null)
  const [openedInitial, setOpenedInitial] = useState<string | null>(null)
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60000)
    return () => window.clearInterval(timer)
  }, [])
  const work = useWork(caseId, {
    taskStatus: statusFilter,
    assigneeUserId: assigneeFilter === "all" ? undefined : assigneeFilter,
  })
  const members = useCaseMembers(caseId).data ?? []
  const update = useUpdateTask(caseId)
  const removeTask = useDeleteTask(caseId)
  const removeDeadline = useDeleteDeadline(caseId)
  const initial = useQuery({
    queryKey: ["workspace", caseId, "work-item", initialItemId],
    enabled: Boolean(initialItemId),
    retry: false,
    queryFn: async (): Promise<Selection> => {
      // Shared links can point beyond the first page or current filters.
      const [task, dates] = await Promise.allSettled([
        workspaceAPI.getTask(caseId, initialItemId!),
        deadlinesAPI.list(caseId),
      ])
      if (task.status === "fulfilled") return { type: "task", task: task.value }
      const deadline =
        dates.status === "fulfilled"
          ? dates.value.find((d) => d.id === initialItemId)
          : undefined
      if (deadline) return { type: "deadline", deadline }
      throw new Error(
        "This item could not be loaded. It may have been removed or you may not have access."
      )
    },
  })
  useEffect(() => {
    if (initial.data && openedInitial !== initialItemId) {
      setSelection(initial.data)
      setOpenedInitial(initialItemId)
    }
  }, [initial.data, initialItemId, openedInitial])
  const tasks = useMemo(() => work.data?.tasks ?? [], [work.data?.tasks])
  const deadlines = useMemo(
    () => work.data?.deadlines ?? [],
    [work.data?.deadlines]
  )
  const items = useMemo(() => {
    const list = [
      ...(typeFilter === "deadlines"
        ? []
        : tasks.map((task) => ({
            id: task.id,
            title: task.title,
            date: task.due_at ?? null,
            selection: { type: "task", task } as Selection,
          }))),
      ...(typeFilter === "tasks" ||
      statusFilter !== "all" ||
      assigneeFilter !== "all"
        ? []
        : deadlines.map((deadline) => ({
            id: deadline.id,
            title: deadline.name,
            date: deadline.due_date,
            selection: { type: "deadline", deadline } as Selection,
          }))),
    ]
    return list.sort(
      (a, b) =>
        (a.date
          ? new Date(
              a.date.includes("T") ? a.date : `${a.date}T00:00:00`
            ).getTime()
          : Infinity) -
          (b.date
            ? new Date(
                b.date.includes("T") ? b.date : `${b.date}T00:00:00`
              ).getTime()
            : Infinity) || a.title.localeCompare(b.title)
    )
  }, [tasks, deadlines, typeFilter, statusFilter, assigneeFilter])
  const changeStatus = async (task: InvestigationTask, status: TaskStatus) => {
    try {
      await update.mutateAsync({ taskId: task.id, updates: { status } })
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }
  const remove = async (item: (typeof items)[number]) => {
    if (
      !window.confirm(
        `Remove “${item.title}”?${item.selection.type === "deadline" ? " Linked tasks will lose their deadline link." : ""}`
      )
    )
      return
    try {
      if (item.selection.type === "task") await removeTask.mutateAsync(item.id)
      else await removeDeadline.mutateAsync(item.id)
      toast.success("Item removed")
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <CalendarClock className="size-4" />
            Deadlines
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Tasks and case dates together, including tasks without a due date.
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {work.data?.task_total ?? 0} tasks ·{" "}
            {work.data?.deadline_total ?? 0} deadlines
          </p>
        </div>
        {canEdit && (
          <Button size="sm" onClick={() => setAdding(true)}>
            <Plus className="size-3.5" />
            Add new
          </Button>
        )}
      </div>
      {adding && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3">
          <span className="text-xs">What would you like to add?</span>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setSelection({ type: "task" })
              setAdding(false)
            }}
          >
            <CheckSquare className="size-3.5" />
            Task
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setSelection({ type: "deadline" })
              setAdding(false)
            }}
          >
            <CalendarClock className="size-3.5" />
            Deadline
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
            Cancel
          </Button>
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        <label className="text-xs">
          Type
          <select
            aria-label="Type"
            className="ml-2 h-8 rounded-md border bg-background px-2"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="all">All</option>
            <option value="tasks">Tasks</option>
            <option value="deadlines">Deadlines</option>
          </select>
        </label>
        <label className="text-xs">
          Status
          <select
            aria-label="Status"
            className="ml-2 h-8 rounded-md border bg-background px-2"
            value={statusFilter}
            onChange={(e) =>
              setStatusFilter(e.target.value as TaskStatus | "all")
            }
          >
            <option value="all">All statuses</option>
            <option value="todo">To Do</option>
            <option value="in_progress">In Progress</option>
            <option value="done">Done</option>
          </select>
        </label>
        <label className="text-xs">
          Assignee
          <select
            aria-label="Assignee"
            className="ml-2 h-8 rounded-md border bg-background px-2"
            value={assigneeFilter}
            onChange={(e) => setAssigneeFilter(e.target.value)}
          >
            <option value="all">All case members</option>
            {members.map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.user_name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {(statusFilter !== "all" || assigneeFilter !== "all") && (
        <p className="text-xs text-muted-foreground">
          Status and assignee apply to tasks. Clear these filters to include
          case deadlines.
        </p>
      )}
      {initial.isError && (
        <p role="alert" className="text-xs text-destructive">
          {errorMessage(initial.error)}{" "}
          <Button variant="ghost" size="sm" onClick={() => initial.refetch()}>
            Try again
          </Button>
        </p>
      )}
      {work.isError && (
        <div role="alert" className="rounded-lg border p-4 text-sm">
          The list could not be loaded.{" "}
          <Button variant="outline" onClick={() => work.refetch()}>
            Try again
          </Button>
        </div>
      )}
      {work.isLoading ? (
        <div className="h-32 animate-pulse rounded-lg bg-muted" />
      ) : !items.length && !work.isError ? (
        <p className="rounded-lg border border-dashed p-8 text-center text-xs text-muted-foreground">
          No tasks or deadlines match these filters.
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((item, i) => (
            <div key={`${item.selection.type}-${item.id}`}>
              {!item.date && (i === 0 || items[i - 1].date) && (
                <h3 className="mb-2 mt-5 text-xs font-semibold">No due date</h3>
              )}
              <div
                className={cn(
                  "flex items-start gap-3 rounded-lg border bg-card p-3",
                  item.id === initialItemId && "ring-2 ring-ring"
                )}
              >
                {item.selection.type === "task" && (
                  <Checkbox
                    className="mt-1"
                    aria-label={`Mark ${item.title} complete`}
                    checked={item.selection.task?.status === "done"}
                    disabled={!canEdit || update.isPending}
                    onCheckedChange={() =>
                      changeStatus(
                        item.selection.type === "task"
                          ? item.selection.task!
                          : tasks[0],
                        item.selection.type === "task" &&
                          item.selection.task?.status === "done"
                          ? "todo"
                          : "done"
                      )
                    }
                  />
                )}
                <button
                  className="min-w-0 flex-1 text-left"
                  onClick={() => setSelection(item.selection)}
                  aria-label={`Open ${item.title}`}
                >
                  <span className="break-words text-sm font-medium">
                    {item.title}
                  </span>
                  <span className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    <Badge variant="outline">
                      {item.selection.type === "task" ? "Task" : "Deadline"}
                    </Badge>
                    <span>{workDateLabel(item.date, now)}</span>
                  </span>
                  {item.selection.type === "task" && (
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {
                        {
                          todo: "To Do",
                          in_progress: "In Progress",
                          done: "Done",
                        }[item.selection.task?.status ?? "todo"]
                      }{" "}
                      · {item.selection.task?.assignee_name || "Unassigned"}
                      {item.selection.task?.priority !== "standard"
                        ? ` · ${item.selection.task?.priority}`
                        : ""}
                      {item.selection.task?.subtask_progress.total
                        ? ` · ${item.selection.task.subtask_progress.done}/${item.selection.task.subtask_progress.total} subtasks done`
                        : ""}
                    </span>
                  )}
                </button>
                {canEdit && (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    disabled={removeTask.isPending || removeDeadline.isPending}
                    aria-label={`Delete ${item.title}`}
                    onClick={() => remove(item)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {work.hasNextPage && (
        <Button
          variant="outline"
          disabled={work.isFetchingNextPage}
          onClick={() => work.fetchNextPage()}
        >
          {work.isFetchingNextPage
            ? "Loading…"
            : "Load more tasks and deadlines"}
        </Button>
      )}
      {selection && (
        <WorkItemDialog
          key={`${selection.type}-${selection.type === "task" ? (selection.task?.id ?? "new") : (selection.deadline?.id ?? "new")}`}
          caseId={caseId}
          selection={selection}
          canEdit={canEdit}
          tasks={tasks}
          deadlines={deadlines}
          onClose={() => setSelection(null)}
        />
      )}
    </div>
  )
}
