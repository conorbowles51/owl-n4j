import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { FileEntityLinker } from "./FileEntityLinker"

const mocks = vi.hoisted(() => ({
  addEvidence: vi.fn(),
  removeEvidence: vi.fn(),
  refetch: vi.fn(),
  invalidateQueries: vi.fn(),
}))

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({
    data: {
      dossiers: [
        {
          id: "dossier-1",
          dossier_type: "person",
          display_name: "Henry Example",
        },
      ],
    },
    refetch: mocks.refetch,
  }),
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}))

vi.mock("@/features/dossiers/api", () => ({
  dossiersAPI: {
    addEvidence: mocks.addEvidence,
    removeEvidence: mocks.removeEvidence,
  },
}))

vi.mock("@/features/dossiers/components/DossierPicker", () => ({
  DossierTypeBadge: ({ type }: { type: string }) => <span>{type}</span>,
  DossierPicker: ({
    onSelect,
  }: {
    onSelect: (dossier: {
      id: string
      dossier_type: string
      display_name: string
    }) => void
  }) => (
    <button
      type="button"
      onClick={() =>
        onSelect({
          id: "dossier-2",
          dossier_type: "organisation",
          display_name: "Example Ltd",
        })
      }
    >
      Select Example Ltd
    </button>
  ),
}))

describe("FileEntityLinker", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.addEvidence.mockResolvedValue({})
    mocks.removeEvidence.mockResolvedValue({})
    mocks.refetch.mockResolvedValue({})
    mocks.invalidateQueries.mockResolvedValue(undefined)
  })

  it("adds and removes evidence through canonical Dossier routes", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <FileEntityLinker
        caseId="case-1"
        evidenceId="evidence-1"
        onChange={onChange}
      />
    )

    expect(screen.getByText("Henry Example")).toBeInTheDocument()
    await user.click(screen.getByTitle("Remove Dossier link"))
    await waitFor(() =>
      expect(mocks.removeEvidence).toHaveBeenCalledWith(
        "dossier-1",
        "evidence-1"
      )
    )
    expect(onChange).toHaveBeenCalledWith([])

    await user.click(screen.getByRole("button", { name: "Dossier" }))
    await user.click(screen.getByRole("button", { name: "Select Example Ltd" }))
    await waitFor(() =>
      expect(mocks.addEvidence).toHaveBeenCalledWith("dossier-2", ["evidence-1"])
    )
    expect(onChange).toHaveBeenLastCalledWith(["dossier-1", "dossier-2"])
  })
})
