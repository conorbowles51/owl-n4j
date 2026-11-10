import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { CaseWorkResponse } from "../api"
import { TasksSection } from "./TasksSection"
import { workDateLabel } from "../work-date"

const mocks = vi.hoisted(() => ({
  work: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  updateDeadline: vi.fn(),
}))

const work: CaseWorkResponse = {
  tasks: [
    {
      id: "task-parent",
      case_id: "case-1",
      title: "Trace transfers",
      description: "Build the source-of-funds chain.",
      status: "in_progress",
      priority: "urgent",
      assignee_user_id: "editor-1",
      assignee_name: "Alex Editor",
      due_at: "2026-09-20T12:00:00Z",
      parent_task_id: null,
      deadline_id: "deadline-1",
      deadline_name: "Disclosure",
      links: [],
      subtask_progress: { done: 1, total: 2 },
    },
    {
      id: "task-child",
      case_id: "case-1",
      title: "Review statement",
      status: "done",
      priority: "standard",
      parent_task_id: "task-parent",
      links: [],
      subtask_progress: { done: 0, total: 0 },
    },
  ],
  task_total: 2,
  deadlines: [
    {
      id: "deadline-1",
      case_id: "case-1",
      name: "Disclosure",
      due_date: "2026-10-01",
    },
  ],
  deadline_total: 1,
  bounded: true,
  limit: 100,
}

vi.mock("../hooks/use-workspace", () => ({
  useWork: (...args: unknown[]) => mocks.work(...args),
  useCreateTask: () => ({ mutateAsync: mocks.create, isPending: false }),
  useUpdateTask: () => ({ mutateAsync: mocks.update, isPending: false }),
  useDeleteTask: () => ({ mutateAsync: mocks.remove, isPending: false }),
}))

vi.mock("@/features/cases/hooks/use-case-members", () => ({
  useCaseMembers: () => ({
    data: [
      {
        user_id: "editor-1",
        user_name: "Alex Editor",
        user_email: "alex@example.test",
        preset: "editor",
        permissions: {},
      },
    ],
  }),
}))

vi.mock("@tanstack/react-query", () => ({
  useQuery: ({ queryKey }: { queryKey: string[] }) => ({
    data:
      queryKey[0] === "deadlines"
        ? work.deadlines
        : queryKey.includes("parent-options")
          ? {
              tasks: work.tasks,
              total: work.tasks.length,
              limit: 50,
              offset: 0,
            }
          : null,
  }),
}))
vi.mock("@/features/cases/hooks/use-deadlines", () => ({
  useCreateDeadline: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateDeadline: () => ({
    mutateAsync: mocks.updateDeadline,
    isPending: false,
  }),
  useDeleteDeadline: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

describe("TasksSection", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    )
    mocks.work.mockReset().mockReturnValue({ data: work, isLoading: false })
    mocks.create.mockReset().mockResolvedValue({ id: "new-task" })
    mocks.update.mockReset().mockResolvedValue({})
    mocks.remove.mockReset().mockResolvedValue({})
    mocks.updateDeadline.mockReset().mockResolvedValue({})
  })
  afterEach(() => vi.unstubAllGlobals())
  it("includes tasks without due dates alongside deadlines by default", () => {
    render(<TasksSection caseId="case-1" canEdit />)
    expect(
      screen.getByRole("button", { name: "Open Trace transfers" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Open Disclosure" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Open Review statement" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Completed" })
    ).toBeInTheDocument()
  })
  it("creates a task from the shared Add new action and retains its links", async () => {
    render(<TasksSection caseId="case-1" canEdit />)
    fireEvent.click(screen.getByRole("button", { name: "Add new" }))
    fireEvent.click(screen.getByRole("button", { name: "Task" }))
    fireEvent.change(screen.getByLabelText("Task title"), {
      target: { value: "Interview account signatory" },
    })
    fireEvent.change(screen.getByLabelText("Task assignee"), {
      target: { value: "editor-1" },
    })
    fireEvent.change(screen.getByLabelText("Linked deadline"), {
      target: { value: "deadline-1" },
    })
    fireEvent.change(screen.getByLabelText("Parent task"), {
      target: { value: "task-parent" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Create task" }))
    await waitFor(() =>
      expect(mocks.create).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Interview account signatory",
          assignee_user_id: "editor-1",
          deadline_id: "deadline-1",
          parent_task_id: "task-parent",
        })
      )
    )
  })
  it("keeps viewers read only and makes type a filter", () => {
    render(<TasksSection caseId="case-1" canEdit={false} />)
    expect(
      screen.queryByRole("button", { name: "Add new" })
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole("checkbox", { name: "Mark Trace transfers complete" })
    ).toBeDisabled()
    fireEvent.change(screen.getByLabelText("Type"), {
      target: { value: "deadlines" },
    })
    expect(
      screen.queryByRole("button", { name: "Open Trace transfers" })
    ).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Open Disclosure" }))
    expect(
      screen.getByRole("heading", { name: "View deadline" })
    ).toBeInTheDocument()
    expect(screen.getByLabelText("Deadline name")).toBeDisabled()
  })
  it("retains entries after a failed save so the user can retry", async () => {
    mocks.create.mockRejectedValueOnce(new Error("Service unavailable"))
    render(<TasksSection caseId="case-1" canEdit />)
    fireEvent.click(screen.getByRole("button", { name: "Add new" }))
    fireEvent.click(screen.getByRole("button", { name: "Task" }))
    fireEvent.change(screen.getByLabelText("Task title"), {
      target: { value: "Keep my draft" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Create task" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Service unavailable"
    )
    expect(screen.getByLabelText("Task title")).toHaveValue("Keep my draft")
    fireEvent.click(screen.getByRole("button", { name: "Create task" }))
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    )
  })
  it("treats today's date-only deadline as Today instead of Overdue", () => {
    expect(workDateLabel("2026-10-19", new Date(2026, 9, 19, 16))).toMatch(
      /^Today/
    )
    expect(workDateLabel("2026-10-18", new Date(2026, 9, 19, 16))).toMatch(
      /^Overdue/
    )
    expect(workDateLabel(null)).toBe("No due date")
    expect(
      workDateLabel("2026-10-18", new Date(2026, 9, 19, 16), true)
    ).not.toContain("Overdue")
    expect(workDateLabel("invalid-date")).toBe("Date unavailable")
  })

  it("completes a deadline without deleting it or completing its linked tasks", async () => {
    render(<TasksSection caseId="case-1" canEdit />)
    fireEvent.click(
      screen.getByRole("checkbox", { name: "Mark Disclosure complete" })
    )
    await waitFor(() =>
      expect(mocks.updateDeadline).toHaveBeenCalledWith({
        deadlineId: "deadline-1",
        data: { completed: true },
      })
    )
    expect(mocks.update).not.toHaveBeenCalled()
    expect(mocks.remove).not.toHaveBeenCalled()
  })

  it("keeps a failed completion visible and retries the same change", async () => {
    mocks.updateDeadline.mockRejectedValueOnce(
      new Error("Connection interrupted")
    )
    render(<TasksSection caseId="case-1" canEdit />)
    fireEvent.click(
      screen.getByRole("checkbox", { name: "Mark Disclosure complete" })
    )
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "was not changed"
    )
    expect(
      screen.getByRole("checkbox", { name: "Mark Disclosure complete" })
    ).not.toBeChecked()
    fireEvent.click(screen.getByRole("button", { name: "Try again" }))
    await waitFor(() => expect(mocks.updateDeadline).toHaveBeenCalledTimes(2))
    expect(mocks.updateDeadline.mock.calls[1][0]).toEqual({
      deadlineId: "deadline-1",
      data: { completed: true },
    })
  })

  it("reopens completed deadlines and does not call their old dates overdue", async () => {
    mocks.work.mockReturnValue({
      data: {
        ...work,
        deadlines: [
          { ...work.deadlines[0], completed_at: "2026-10-01T12:00:00Z" },
        ],
      },
    })
    render(<TasksSection caseId="case-1" canEdit />)
    expect(
      screen.getByRole("button", { name: "Open Disclosure" })
    ).not.toHaveTextContent("Overdue")
    fireEvent.click(screen.getByRole("checkbox", { name: "Reopen Disclosure" }))
    await waitFor(() =>
      expect(mocks.updateDeadline).toHaveBeenCalledWith({
        deadlineId: "deadline-1",
        data: { completed: false },
      })
    )
  })

  it("clears task-only filters when selecting deadlines", () => {
    render(<TasksSection caseId="case-1" canEdit />)
    fireEvent.change(screen.getByLabelText("Assignee"), {
      target: { value: "editor-1" },
    })
    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "in_progress" },
    })
    fireEvent.change(screen.getByLabelText("Type"), {
      target: { value: "deadlines" },
    })
    expect(
      screen.getByRole("button", { name: "Open Disclosure" })
    ).toBeVisible()
    expect(screen.getByLabelText("Assignee")).toBeDisabled()
    expect(screen.getByLabelText("Status")).toHaveValue("all")
  })

  it("uses case-wide linking choices even when the work list is filtered empty", () => {
    mocks.work.mockReturnValue({ data: { ...work, tasks: [], deadlines: [] } })
    render(<TasksSection caseId="case-1" canEdit />)
    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "in_progress" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Add new" }))
    fireEvent.click(screen.getByRole("button", { name: "Task" }))
    expect(
      screen.getByRole("option", { name: /Disclosure/ })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("option", { name: "Trace transfers" })
    ).toBeInTheDocument()
  })
})
