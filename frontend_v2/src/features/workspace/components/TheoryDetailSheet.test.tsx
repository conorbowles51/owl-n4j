import { type ReactElement } from "react"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api-client"
import { TheoryDetailSheet } from "./TheoryDetailSheet"

class ResizeObserverMock {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

vi.stubGlobal("ResizeObserver", ResizeObserverMock)

const sheetMocks = vi.hoisted(() => ({
  buildMutate: vi.fn(),
  deleteMutate: vi.fn(),
  updateMutate: vi.fn(),
  getTheoryTimeline: vi.fn(),
}))

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>()
  return {
    ...actual,
    workspaceAPI: {
      ...actual.workspaceAPI,
      getTheoryTimeline: sheetMocks.getTheoryTimeline,
    },
  }
})

vi.mock("../hooks/use-workspace", () => ({
  useBuildWorkspaceGraph: () => ({
    isPending: false,
    mutate: sheetMocks.buildMutate,
  }),
  useDeleteTheory: () => ({
    isPending: false,
    mutate: sheetMocks.deleteMutate,
  }),
  useUpdateTheory: () => ({
    isPending: false,
    mutate: sheetMocks.updateMutate,
  }),
}))

function renderSheet(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

const baseTheory = {
  id: "theory-1",
  theory_id: "theory-1",
  title: "Local theory",
  type: "PRIMARY" as const,
  confidence_score: 50,
  hypothesis: "Local original",
  supporting_evidence: ["local evidence"],
  counter_arguments: ["local counter"],
  next_steps: ["local step"],
  privilege_level: "PUBLIC" as const,
  version: 1,
}

describe("TheoryDetailSheet conflicts", () => {
  beforeEach(() => {
    sheetMocks.buildMutate.mockReset()
    sheetMocks.deleteMutate.mockReset()
    sheetMocks.updateMutate.mockReset()
    sheetMocks.getTheoryTimeline.mockReset()
    sheetMocks.getTheoryTimeline.mockResolvedValue([])
  })

  it("keeps the local draft and retries with the current server version", async () => {
    const close = vi.fn()
    const conflictError = new ApiError("Version conflict", 409, {
      detail: {
        code: "workspace_version_conflict",
        entity: "theory",
        current_version: 2,
        current: {
          id: "theory-1",
          theory_id: "theory-1",
          title: "Server theory",
          type: "PRIMARY",
          confidence_score: 75,
          hypothesis: "Server edit",
          supporting_evidence: ["server evidence"],
          counter_arguments: ["server counter"],
          next_steps: ["server step"],
          privilege_level: "PUBLIC",
          version: 2,
        },
      },
    })

    sheetMocks.updateMutate
      .mockImplementationOnce((_variables, options) => {
        options.onError(conflictError)
      })
      .mockImplementationOnce(() => {})

    renderSheet(
      <TheoryDetailSheet
        caseId="case-1"
        theory={baseTheory}
        open
        onOpenChange={close}
      />,
    )

    fireEvent.change(screen.getByDisplayValue("Local original"), {
      target: { value: "Local edit" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    expect(await screen.findByText("Current saved version")).toBeInTheDocument()
    expect(screen.getByText(/Server edit/)).toBeInTheDocument()
    expect(screen.getByText(/Local edit/, { selector: "pre" })).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Merge manually" }))
    fireEvent.click(screen.getByRole("button", { name: "Save" }))

    await waitFor(() => expect(sheetMocks.updateMutate).toHaveBeenCalledTimes(2))
    expect(sheetMocks.updateMutate.mock.calls[1][0]).toMatchObject({
      theoryId: "theory-1",
      updates: {
        hypothesis: "Local edit",
        expected_version: 2,
      },
    })
    expect(close).not.toHaveBeenCalled()
  })

  it("blocks closing while dirty and allows it after reverting changes", () => {
    const close = vi.fn()

    renderSheet(
      <TheoryDetailSheet
        caseId="case-1"
        theory={baseTheory}
        open
        onOpenChange={close}
      />,
    )

    fireEvent.change(screen.getByDisplayValue("Local original"), {
      target: { value: "Local edit" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Close" }))

    expect(close).not.toHaveBeenCalled()

    fireEvent.change(screen.getByDisplayValue("Local edit"), {
      target: { value: "Local original" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Close" }))

    expect(close).toHaveBeenCalledWith(false)
  })
})
