import { HandOverDialog } from "@/features/conversations/HandOverDialog"
import { useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  CalendarClock,
  CheckSquare,
  ChevronRight,
  LoaderCircle,
  Plus,
  Trash2,
} from "lucide-react"
import { toast } from "sonner"
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
import { useUnsavedHistoryGuard } from "@/hooks/use-unsaved-history-guard"
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

import { workDateGroup, workDateLabel } from "../work-date"
import { TaskLinkedContext } from "./TaskLinkedContext"

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
  if (Number.isNaN(date.getTime())) return ""
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)
}

function WorkItemDialog({
  caseId,
  selection,
  canEdit,
  onClose,
}: {
  caseId: string
  selection: Selection
  canEdit: boolean
  onClose: () => void
}) {
  const task = selection.type === "task" ? selection.task : undefined
  const deadline =
    selection.type === "deadline" ? selection.deadline : undefined
  const existing = Boolean(task || deadline)
  const members = useCaseMembers(caseId).data ?? []
  const [parentSearch, setParentSearch] = useState("")
  const [parentOffset, setParentOffset] = useState(0)
  const [chosenParent, setChosenParent] = useState<InvestigationTask>()
  const parentOptions = useQuery({
    queryKey: [
      "workspace",
      caseId,
      "tasks",
      "parent-options",
      parentSearch,
      parentOffset,
    ],
    queryFn: () =>
      workspaceAPI.getParentTaskOptions(caseId, parentSearch, parentOffset),
    enabled: selection.type === "task",
  })
  const deadlineOptions = useQuery({
    queryKey: ["deadlines", caseId],
    queryFn: () => deadlinesAPI.list(caseId),
    enabled: selection.type === "task",
  })
  const tasks = parentOptions.data?.tasks ?? []
  const deadlines = deadlineOptions.data ?? []
  // A phone review task is passed on with a note of where it stands (07 J-15 step 4), not by changing the assignee.
  const [handingOver, setHandingOver] = useState(false)
  // This form still holds the old assignee: it closes after a hand-over, so a later Save cannot put the task back.
  const [handedOver, setHandedOver] = useState(false)
  const canHandOver =
    canEdit &&
    task?.status !== "done" &&
    (task?.links ?? []).some(
      (l) =>
        l.source_anchor &&
        ("review_split" in l.source_anchor ||
          "second_pass" in l.source_anchor ||
          "reading_recheck" in l.source_anchor)
    )
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
  const [completed, setCompleted] = useState(Boolean(deadline?.completed_at))
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
    completed,
  ])
  const [original] = useState(snapshot)
  const dirty = original !== snapshot
  const busy =
    createTask.isPending ||
    updateTask.isPending ||
    createDeadline.isPending ||
    updateDeadline.isPending
  useUnsavedHistoryGuard(
    dirty,
    "Discard your unsaved task or deadline changes?"
  )
  const close = () => {
    if (!busy && (!dirty || window.confirm("Discard your unsaved changes?")))
      onClose()
  }
  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    setError("")
    try {
      if (selection.type === "deadline") {
        const data = {
          name: title.trim(),
          due_date: dueDate,
          ...(deadline ? { completed } : {}),
        }
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
      <DialogContent guardTypedContent={false} className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {canEdit ? (existing ? "Edit" : "New") : "View"} {selection.type}
          </DialogTitle>
          <DialogDescription>
            {selection.type === "task"
              ? "Assign work, set an optional due date and link it to a case deadline."
              : "Track a case date, then mark it complete when the work is finished. Linked tasks keep their own status."}
          </DialogDescription>
        </DialogHeader>
        {task && (
          <TaskLinkedContext
            caseId={caseId}
            links={task.links}
            canEdit={canEdit}
            onBeforeNavigate={() =>
              !busy &&
              (!dirty || window.confirm("Discard your unsaved task changes?"))
            }
          />
        )}
        <form onSubmit={save} className="space-y-3">
          <fieldset disabled={!canEdit || busy} className="space-y-3">
            <label className="block space-y-1 text-xs">
              {selection.type === "task" ? "Task title" : "Deadline name"}
              <Input
                aria-label={
                  selection.type === "task" ? "Task title" : "Deadline name"
                }
                required
                maxLength={255}
                autoFocus
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            {selection.type === "deadline" ? (
              <div className="space-y-4">
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
                {deadline && (
                  <label className="flex min-h-10 items-center gap-3 text-sm">
                    <Checkbox
                      checked={completed}
                      onCheckedChange={(value) => setCompleted(value === true)}
                      aria-label="Deadline completed"
                    />
                    Completed
                  </label>
                )}
              </div>
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
                        {d.completed_at ? " · Completed" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                {deadlineOptions.isLoading && (
                  <p role="status" className="text-xs text-muted-foreground">
                    Loading case deadlines…
                  </p>
                )}
                {deadlineOptions.isError && (
                  <p role="alert" className="text-xs text-destructive">
                    Deadline choices could not be loaded. Your current link is
                    unchanged.{" "}
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => void deadlineOptions.refetch()}
                    >
                      Retry deadline choices
                    </Button>
                  </p>
                )}
                <label className="block text-xs">
                  Parent task
                  <select
                    aria-label="Parent task"
                    className="mt-1 h-9 w-full rounded-md border bg-background px-2"
                    value={parentId}
                    onChange={(e) => {
                      setParentId(e.target.value)
                      setChosenParent(
                        tasks.find(
                          (candidate) => candidate.id === e.target.value
                        )
                      )
                    }}
                  >
                    <option value="">Top-level task</option>
                    {parentId &&
                      !tasks.some(
                        (t) =>
                          t.id === parentId &&
                          !t.parent_task_id &&
                          t.status !== "done"
                      ) && (
                        <option value={parentId}>
                          {chosenParent?.title || "Existing parent task"}
                        </option>
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
                <div className="space-y-2">
                  <Input
                    aria-label="Search parent tasks"
                    placeholder="Search parent tasks across the case…"
                    maxLength={200}
                    value={parentSearch}
                    onChange={(event) => {
                      setParentSearch(event.target.value)
                      setParentOffset(0)
                    }}
                  />
                  {parentOptions.isLoading && (
                    <p role="status" className="text-xs text-muted-foreground">
                      Loading parent tasks…
                    </p>
                  )}
                  {parentOptions.isError && (
                    <p role="alert" className="text-xs text-destructive">
                      Parent tasks could not be loaded. Your current link is
                      unchanged.{" "}
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => void parentOptions.refetch()}
                      >
                        Retry parent tasks
                      </Button>
                    </p>
                  )}
                  {!!parentOptions.data &&
                    parentOptions.data.total > parentOptions.data.limit && (
                      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled={!parentOffset || parentOptions.isFetching}
                          onClick={() =>
                            setParentOffset(Math.max(0, parentOffset - 50))
                          }
                        >
                          Previous parent tasks
                        </Button>
                        <span className="tabular-nums">
                          Page {Math.floor(parentOffset / 50) + 1}
                        </span>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled={
                            parentOffset + parentOptions.data.limit >=
                              parentOptions.data.total ||
                            parentOptions.isFetching
                          }
                          onClick={() => setParentOffset(parentOffset + 50)}
                        >
                          Next parent tasks
                        </Button>
                      </div>
                    )}
                </div>
              </>
            )}
          </fieldset>
          {error && (
            <p role="alert" className="text-xs text-destructive">
              {error} Your entries are still here.
            </p>
          )}
          <div className="flex justify-end gap-2">
            {canHandOver && (
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => setHandingOver(true)}
              >
                Hand over…
              </Button>
            )}
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
        {task && handingOver && (
          <HandOverDialog
            caseId={caseId}
            taskId={task.id}
            title={task.title}
            open
            onHandedOver={() => setHandedOver(true)}
            onClose={() => (handedOver ? onClose() : setHandingOver(false))}
          />
        )}
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
  const updateDate = useUpdateDeadline(caseId)
  const [pendingIds, setPendingIds] = useState<Set<string>>(() => new Set())
  const [actionError, setActionError] = useState<{
    message: string
    retry: () => Promise<void>
  } | null>(null)
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
    if (!initialItemId && openedInitial) {
      setSelection(null)
      setOpenedInitial(null)
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
            completed: task.status === "done",
            selection: { type: "task", task } as Selection,
          }))),
      ...(typeFilter === "tasks" ||
      statusFilter === "in_progress" ||
      assigneeFilter !== "all"
        ? []
        : deadlines
            .filter(
              (deadline) =>
                statusFilter === "all" ||
                (statusFilter === "done"
                  ? !!deadline.completed_at
                  : !deadline.completed_at)
            )
            .map((deadline) => ({
              id: deadline.id,
              title: deadline.name,
              date: deadline.due_date,
              completed: !!deadline.completed_at,
              selection: { type: "deadline", deadline } as Selection,
            }))),
    ]
    return list.sort(
      (a, b) =>
        Number(a.completed) - Number(b.completed) ||
        (a.date
          ? new Date(
              a.date.includes("T") ? a.date : `${a.date}T00:00:00`
            ).getTime()
          : Infinity) -
          (b.date
            ? new Date(
                b.date.includes("T") ? b.date : `${b.date}T00:00:00`
              ).getTime()
            : Infinity) ||
        a.title.localeCompare(b.title)
    )
  }, [tasks, deadlines, typeFilter, statusFilter, assigneeFilter])
  const setPending = (key: string, pending: boolean) =>
    setPendingIds((current) => {
      const next = new Set(current)
      if (pending) next.add(key)
      else next.delete(key)
      return next
    })
  const changeStatus = async (item: (typeof items)[number]) => {
    const key = `${item.selection.type}-${item.id}`
    setPending(key, true)
    setActionError(null)
    try {
      if (item.selection.type === "task") {
        await update.mutateAsync({
          taskId: item.id,
          updates: { status: item.completed ? "todo" : "done" },
        })
      } else {
        await updateDate.mutateAsync({
          deadlineId: item.id,
          data: { completed: !item.completed },
        })
      }
      toast.success(
        item.completed
          ? `Reopened “${item.title}”`
          : `Completed “${item.title}”`
      )
    } catch (e) {
      setActionError({
        message: `“${item.title}” was not changed. ${errorMessage(e)}`,
        retry: () => changeStatus(item),
      })
    } finally {
      setPending(key, false)
    }
  }
  const remove = async (item: (typeof items)[number], confirmed = false) => {
    if (
      !confirmed &&
      !window.confirm(
        `Remove “${item.title}”?${item.selection.type === "deadline" ? " Linked tasks will lose their deadline link." : ""}`
      )
    )
      return
    const key = `${item.selection.type}-${item.id}`
    setPending(key, true)
    setActionError(null)
    try {
      if (item.selection.type === "task") await removeTask.mutateAsync(item.id)
      else await removeDeadline.mutateAsync(item.id)
      toast.success("Item removed")
    } catch (e) {
      setActionError({
        message: `“${item.title}” could not be removed. ${errorMessage(e)}`,
        retry: () => remove(item, true),
      })
    } finally {
      setPending(key, false)
    }
  }
  const groups = [
    "Overdue",
    "Today",
    "Upcoming",
    "No due date",
    "Completed",
  ] as const
  const filtered =
    typeFilter !== "all" || statusFilter !== "all" || assigneeFilter !== "all"
  const clearFilters = () => {
    setTypeFilter("all")
    setStatusFilter("all")
    setAssigneeFilter("all")
  }
  return (
    <div className="space-y-7">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Keep the investigation moving
          </p>
          <h2 className="font-display text-2xl font-semibold tracking-tight">
            Tasks &amp; deadlines
          </h2>
          <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted-foreground">
            The next actions and important dates, in one place.
          </p>
          <p className="mt-3 text-xs tabular-nums text-muted-foreground">
            {work.data?.task_total ?? 0}{" "}
            {work.data?.task_total === 1 ? "task" : "tasks"} ·{" "}
            {work.data?.deadline_total ?? 0}{" "}
            {work.data?.deadline_total === 1 ? "deadline" : "deadlines"}
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
        <div className="flex flex-wrap items-center gap-2 border-y border-border/60 py-3">
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
      <div className="flex flex-wrap items-end gap-3 border-b border-border/60 pb-4">
        <label className="text-xs">
          Type
          <select
            aria-label="Type"
            className="ml-2 h-10 rounded-md border border-border/70 bg-background px-2"
            value={typeFilter}
            onChange={(e) => {
              setTypeFilter(e.target.value)
              if (e.target.value === "deadlines") {
                setAssigneeFilter("all")
                if (statusFilter === "in_progress") setStatusFilter("all")
              }
            }}
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
            className="ml-2 h-10 rounded-md border border-border/70 bg-background px-2"
            value={statusFilter}
            onChange={(e) =>
              setStatusFilter(e.target.value as TaskStatus | "all")
            }
          >
            <option value="all">All statuses</option>
            <option value="todo">To do / open</option>
            {typeFilter !== "deadlines" && (
              <option value="in_progress">In progress</option>
            )}
            <option value="done">Completed</option>
          </select>
        </label>
        <label className="text-xs">
          Assignee
          <select
            aria-label="Assignee"
            disabled={typeFilter === "deadlines"}
            className="ml-2 h-10 rounded-md border border-border/70 bg-background px-2"
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
        {filtered && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            Clear filters
          </Button>
        )}
      </div>
      {(statusFilter === "in_progress" || assigneeFilter !== "all") && (
        <p className="text-xs text-muted-foreground">
          In-progress and assignee filters show tasks. Clear these filters to
          include case deadlines.
        </p>
      )}
      {actionError && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 border-l-2 border-destructive bg-destructive/5 px-4 py-3 text-sm"
        >
          <p>{actionError.message}</p>
          <Button
            variant="outline"
            size="sm"
            disabled={pendingIds.size > 0}
            onClick={() => void actionError.retry()}
          >
            Try again
          </Button>
        </div>
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
        <div
          role="status"
          aria-label="Loading tasks and deadlines"
          className="space-y-4 py-4"
        >
          {[1, 2, 3].map((row) => (
            <div key={row} className="h-14 animate-pulse rounded bg-muted/40" />
          ))}
        </div>
      ) : !items.length && !work.isError ? (
        <div className="py-12 text-center">
          <CalendarClock
            aria-hidden="true"
            className="mx-auto mb-4 size-6 text-muted-foreground/60"
          />
          <h3 className="font-display text-lg font-medium">
            {filtered
              ? "Nothing matches these filters"
              : "Room for your next move"}
          </h3>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">
            {filtered
              ? "Adjust the filters to see the rest of your work."
              : "Add a task for the next step, or a deadline for an important case date."}
          </p>
          {filtered && (
            <Button variant="ghost" className="mt-3" onClick={clearFilters}>
              Show all work
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-8">
          {groups.map((group) => {
            const grouped = items.filter(
              (item) => workDateGroup(item.date, item.completed, now) === group
            )
            if (!grouped.length) return null
            return (
              <section key={group} aria-label={group}>
                <h3
                  className={cn(
                    "mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground",
                    group === "Overdue" && "text-destructive"
                  )}
                >
                  <span>{group}</span>
                  <span
                    aria-hidden="true"
                    className="font-normal tabular-nums tracking-normal opacity-70"
                  >
                    {grouped.length}
                  </span>
                </h3>
                <div className="divide-y divide-border/50 border-y border-border/50">
                  {grouped.map((item) => {
                    const key = `${item.selection.type}-${item.id}`
                    const pending = pendingIds.has(key)
                    const task =
                      item.selection.type === "task"
                        ? item.selection.task
                        : undefined
                    return (
                      <div
                        key={key}
                        className={cn(
                          "group flex items-start gap-3 py-4 sm:gap-4",
                          item.id === initialItemId &&
                            "rounded-md bg-accent/20 px-3 ring-1 ring-ring/50"
                        )}
                      >
                        <div className="relative flex size-10 shrink-0 items-center justify-center">
                          {pending && (
                            <LoaderCircle
                              aria-label={`Saving ${item.title}`}
                              className="absolute size-4 animate-spin text-muted-foreground"
                            />
                          )}
                          <Checkbox
                            className={cn(
                              "relative size-[18px] after:absolute after:-inset-3 after:content-['']",
                              pending && "opacity-0"
                            )}
                            aria-label={
                              item.completed
                                ? `Reopen ${item.title}`
                                : `Mark ${item.title} complete`
                            }
                            checked={item.completed}
                            disabled={!canEdit || pending}
                            aria-busy={pending}
                            onCheckedChange={() => void changeStatus(item)}
                          />
                        </div>
                        <button
                          className="min-w-0 flex-1 rounded-sm py-1 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          onClick={() => setSelection(item.selection)}
                          disabled={pending}
                          aria-label={`Open ${item.title}`}
                        >
                          <span
                            className={cn(
                              "block break-words text-sm font-medium leading-6 transition-colors group-hover:text-primary",
                              item.completed &&
                                "text-muted-foreground line-through decoration-muted-foreground/40"
                            )}
                          >
                            {item.title}
                          </span>
                          <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs leading-5 text-muted-foreground">
                            <span className="inline-flex items-center gap-1.5">
                              {task ? (
                                <CheckSquare
                                  aria-hidden="true"
                                  className="size-3"
                                />
                              ) : (
                                <CalendarClock
                                  aria-hidden="true"
                                  className="size-3"
                                />
                              )}
                              {task ? "Task" : "Deadline"}
                            </span>
                            {item.date && (
                              <span
                                className={cn(
                                  !item.completed &&
                                    group === "Overdue" &&
                                    "text-destructive"
                                )}
                              >
                                {workDateLabel(item.date, now, item.completed)}
                              </span>
                            )}
                            {task && (
                              <>
                                <span>
                                  {task.assignee_name || "Unassigned"}
                                </span>
                                {task.status === "in_progress" && (
                                  <span className="text-primary">
                                    In progress
                                  </span>
                                )}
                                {(task.priority === "high" ||
                                  task.priority === "urgent") && (
                                  <span className="font-medium capitalize">
                                    {task.priority} priority
                                  </span>
                                )}
                                {!!task.subtask_progress.total && (
                                  <span>
                                    {task.subtask_progress.done}/
                                    {task.subtask_progress.total} subtasks done
                                  </span>
                                )}
                              </>
                            )}
                          </span>
                          {task?.deadline_name && (
                            <span className="mt-1 block text-xs text-muted-foreground">
                              For {task.deadline_name}
                            </span>
                          )}
                        </button>
                        <div className="flex shrink-0 items-center gap-1 pt-1">
                          {canEdit && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-10 text-muted-foreground hover:text-destructive"
                              disabled={pending}
                              aria-label={`Delete ${item.title}`}
                              onClick={() => void remove(item)}
                            >
                              <Trash2 className="size-3.5" />
                            </Button>
                          )}
                          <ChevronRight
                            aria-hidden="true"
                            className="hidden size-4 text-muted-foreground/40 sm:block"
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </section>
            )
          })}
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
          onClose={() => setSelection(null)}
        />
      )}
    </div>
  )
}
