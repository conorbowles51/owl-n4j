import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api-client"
import type { CaseworkEntry } from "../casework-api"
import { CaseworkEditor } from "./CaseworkEditor"

const mutations = vi.hoisted(() => ({
  create: vi.fn(),
  update: vi.fn(),
  confidence: vi.fn(),
  significance: vi.fn(),
}))

vi.mock("../hooks/use-casework", () => ({
  useCreateCaseworkEntry: () => ({ mutateAsync: mutations.create, isPending: false }),
  useUpdateCaseworkEntry: () => ({ mutateAsync: mutations.update, isPending: false }),
  useChangeCaseworkConfidence: () => ({ mutateAsync: mutations.confidence, isPending: false }),
  useChangeCaseworkSignificance: () => ({ mutateAsync: mutations.significance, isPending: false }),
}))

vi.mock("./CaseworkComposer", () => ({
  CaseworkComposer: ({ onSubmit }: { onSubmit: (value: unknown) => void }) => (
    <button
      type="button"
      onClick={() =>
        onSubmit({
          entry_type: "note",
          title: null,
          body: "Concurrent draft",
          tags: [],
          significance: null,
          confidence: null,
          confidence_rationale: null,
          links: [],
        })
      }
    >
      Save fixture
    </button>
  ),
}))

const entry: CaseworkEntry = {
  id: "entry-1",
  case_id: "case-1",
  entry_type: "note",
  title: null,
  body: "Original",
  tags: [],
  lifecycle_state: null,
  significance: null,
  confidence: null,
  confidence_rationale: null,
  review_state: "accepted",
  version: 2,
  migration_metadata: {},
  needs_migration_review: false,
  links: [],
}

describe("CaseworkEditor", () => {
  beforeEach(() => {
    Object.values(mutations).forEach((mock) => mock.mockReset())
  })

  it("retains the draft and reports an optimistic concurrency conflict", async () => {
    mutations.update.mockRejectedValue(
      new ApiError("Entry was updated by another investigator", 409),
    )
    const onReload = vi.fn()
    render(
      <CaseworkEditor
        caseId="case-1"
        entry={entry}
        canEdit
        onReload={onReload}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Save fixture" }))

    expect(
      await screen.findByText("This entry changed while you were editing."),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Save fixture" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Reload" }))
    expect(onReload).toHaveBeenCalledTimes(1)
    expect(mutations.update).toHaveBeenCalledWith({
      entryId: "entry-1",
      input: {
        expected_version: 2,
        title: null,
        body: "Concurrent draft",
        tags: [],
        links: [],
      },
    })
  })
})
