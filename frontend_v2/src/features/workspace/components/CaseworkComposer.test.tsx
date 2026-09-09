import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { CaseworkEntry } from "../casework-api"
import { CaseworkComposer } from "./CaseworkComposer"

vi.mock("./CaseworkAttachmentPicker", () => ({
  CaseworkAttachmentPicker: ({ onAttach }: { onAttach: (value: unknown) => void }) => (
    <button
      type="button"
      onClick={() =>
        onAttach({
          target_type: "evidence",
          target_id: "evidence-1",
          target_label: "Bank statement.pdf",
          relationship: "unclassified",
          source_anchor: { page: 4 },
          metadata: { source: "search" },
        })
      }
    >
      Attach fixture
    </button>
  ),
}))

describe("CaseworkComposer", () => {
  it("uses one validated composer for a finding and preserves attachment anchors", async () => {
    const onSubmit = vi.fn()
    render(<CaseworkComposer caseId="case-1" onSubmit={onSubmit} />)

    fireEvent.click(screen.getByRole("button", { name: "Finding" }))
    fireEvent.click(screen.getByRole("button", { name: "Save finding" }))
    expect(screen.getByText("Finding title is required.")).toBeInTheDocument()
    expect(screen.getByText("Add some casework before saving.")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/^Title/), {
      target: { value: "Funds moved after notice" },
    })
    fireEvent.change(screen.getByLabelText("Casework"), {
      target: { value: "The statement records a transfer after notice." },
    })
    fireEvent.click(screen.getByRole("button", { name: "Search" }))
    fireEvent.click(screen.getByRole("button", { name: "Attach fixture" }))
    fireEvent.click(screen.getByRole("button", { name: "Save finding" }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      entry_type: "finding",
      title: "Funds moved after notice",
      significance: "medium",
      links: [
        {
          target_type: "evidence",
          target_label: "Bank statement.pdf",
          relationship: "unclassified",
          source_anchor: { page: 4 },
        },
      ],
    })
  })

  it("requires a rationale when an existing confidence assessment changes", async () => {
    const onSubmit = vi.fn()
    const entry: CaseworkEntry = {
      id: "theory-1",
      case_id: "case-1",
      entry_type: "theory",
      title: "Coordinated disposal",
      body: "The timing may indicate coordination.",
      tags: [],
      lifecycle_state: "investigating",
      significance: null,
      confidence: 40,
      confidence_rationale: null,
      review_state: "accepted",
      version: 3,
      migration_metadata: {},
      needs_migration_review: false,
      links: [],
    }
    render(
      <CaseworkComposer
        caseId="case-1"
        initialEntry={entry}
        onSubmit={onSubmit}
      />,
    )

    fireEvent.click(screen.getByRole("combobox", { name: "Confidence" }))
    fireEvent.click(await screen.findByRole("option", { name: "60%" }))
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }))

    expect(
      screen.getByText("Explain why the confidence assessment changed."),
    ).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("disables authoring controls for a viewer", () => {
    render(
      <CaseworkComposer caseId="case-1" canEdit={false} onSubmit={vi.fn()} />,
    )

    expect(screen.getByLabelText("Casework")).toBeDisabled()
    expect(screen.getByRole("button", { name: "Save note" })).toBeDisabled()
    expect(screen.queryByRole("button", { name: "Search" })).not.toBeInTheDocument()
  })
})
