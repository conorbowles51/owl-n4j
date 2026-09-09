import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { CaseWorkResponse } from "../api"
import { TasksSection } from "./TasksSection"

const mocks = vi.hoisted(() => ({
  work: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
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
  useCreateTask: () => ({ mutate: mocks.create, isPending: false }),
  useUpdateTask: () => ({ mutate: mocks.update, isPending: false }),
  useDeleteTask: () => ({ mutate: mocks.remove, isPending: false }),
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

vi.mock("@/features/cases/components/DeadlinesSection", () => ({
  DeadlinesSection: ({ canEdit }: { canEdit: boolean }) => (
    <div>Deadline editor: {canEdit ? "enabled" : "read only"}</div>
  ),
}))

describe("TasksSection", () => {
  beforeEach(() => {
    mocks.work.mockReset().mockReturnValue({ data: work, isLoading: false })
    mocks.create.mockReset()
    mocks.update.mockReset()
    mocks.remove.mockReset()
  })

  it("combines task dates and canonical deadlines in the bounded upcoming view", () => {
    render(<TasksSection caseId="case-1" canEdit />)

    expect(screen.getByText("Trace transfers")).toBeInTheDocument()
    expect(screen.getByText("Disclosure")).toBeInTheDocument()
    expect(screen.getByText("2 tasks")).toBeInTheDocument()
    expect(mocks.work).toHaveBeenLastCalledWith("case-1", {
      taskStatus: "all",
      assigneeUserId: undefined,
    })
  })

  it("creates a rich task assigned to a current case member with canonical links", () => {
    render(<TasksSection caseId="case-1" canEdit />)
    fireEvent.click(screen.getByRole("button", { name: "tasks" }))
    fireEvent.change(screen.getByLabelText("Task title"), {
      target: { value: "Interview account signatory" },
    })
    fireEvent.change(screen.getByLabelText("Task description"), {
      target: { value: "Resolve the authorisation discrepancy." },
    })
    fireEvent.change(screen.getByLabelText("Task priority"), {
      target: { value: "high" },
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
    fireEvent.click(screen.getByRole("button", { name: /create task/i }))

    expect(mocks.create).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Interview account signatory",
        description: "Resolve the authorisation discrepancy.",
        priority: "high",
        assignee_user_id: "editor-1",
        deadline_id: "deadline-1",
        parent_task_id: "task-parent",
      }),
      expect.any(Object),
    )
    expect(screen.getByText("1/2 subtasks done")).toBeInTheDocument()
  })

  it("keeps viewers read-only while preserving filters and work visibility", () => {
    render(<TasksSection caseId="case-1" canEdit={false} />)
    fireEvent.click(screen.getByRole("button", { name: "tasks" }))

    expect(screen.queryByText("Add task")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /delete trace transfers/i })).not.toBeInTheDocument()
    expect(screen.getByRole("checkbox", { name: /mark trace transfers complete/i })).toBeDisabled()

    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "in_progress" } })
    fireEvent.change(screen.getByLabelText("Assignee"), { target: { value: "editor-1" } })
    expect(mocks.work).toHaveBeenLastCalledWith("case-1", {
      taskStatus: "in_progress",
      assigneeUserId: "editor-1",
    })

    fireEvent.click(screen.getByRole("button", { name: "deadlines" }))
    expect(screen.getByText("Deadline editor: read only")).toBeInTheDocument()
  })
})
