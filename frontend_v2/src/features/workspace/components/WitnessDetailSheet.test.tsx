import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api-client"
import { WitnessDetailSheet } from "./WitnessDetailSheet"

const sheetMocks = vi.hoisted(() => ({
  buildMutate: vi.fn(),
  deleteMutate: vi.fn(),
  updateMutate: vi.fn(),
}))

vi.mock("../hooks/use-workspace", () => ({
  useBuildWorkspaceGraph: () => ({
    isPending: false,
    mutate: sheetMocks.buildMutate,
  }),
  useDeleteWitness: () => ({
    isPending: false,
    mutate: sheetMocks.deleteMutate,
  }),
  useUpdateWitness: () => ({
    isPending: false,
    mutate: sheetMocks.updateMutate,
  }),
}))

const baseWitness = {
  id: "witness-1",
  witness_id: "witness-1",
  name: "Local witness",
  role: "Observer",
  organization: "Local org",
  category: "NEUTRAL" as const,
  credibility_rating: 3,
  statement_summary: "Local original",
  risk_assessment: "Local risk",
  strategy_notes: "Local strategy",
  version: 1,
}

describe("WitnessDetailSheet conflicts", () => {
  beforeEach(() => {
    sheetMocks.buildMutate.mockReset()
    sheetMocks.deleteMutate.mockReset()
    sheetMocks.updateMutate.mockReset()
  })

  it("keeps the local draft and retries with the current server version", async () => {
    const close = vi.fn()
    const conflictError = new ApiError("Version conflict", 409, {
      detail: {
        code: "workspace_version_conflict",
        entity: "witness",
        current_version: 2,
        current: {
          id: "witness-1",
          witness_id: "witness-1",
          name: "Server witness",
          role: "Server role",
          organization: "Server org",
          category: "FRIENDLY",
          credibility_rating: 4,
          statement_summary: "Server edit",
          risk_assessment: "Server risk",
          strategy_notes: "Server strategy",
          version: 2,
        },
      },
    })

    sheetMocks.updateMutate
      .mockImplementationOnce((_variables, options) => {
        options.onError(conflictError)
      })
      .mockImplementationOnce(() => {})

    render(
      <MemoryRouter>
        <WitnessDetailSheet
          caseId="case-1"
          witness={baseWitness}
          open
          onOpenChange={close}
        />
      </MemoryRouter>,
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
      witnessId: "witness-1",
      updates: {
        statement_summary: "Local edit",
        expected_version: 2,
      },
    })
    expect(close).not.toHaveBeenCalled()
  })

  it("blocks closing while dirty and allows it after reverting changes", () => {
    const close = vi.fn()

    render(
      <MemoryRouter>
        <WitnessDetailSheet
          caseId="case-1"
          witness={baseWitness}
          open
          onOpenChange={close}
        />
      </MemoryRouter>,
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
