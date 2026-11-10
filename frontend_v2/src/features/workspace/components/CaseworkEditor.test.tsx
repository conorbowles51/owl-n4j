import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api-client"
import type { CaseworkEntry } from "../casework-api"
import { CaseworkEditor } from "./CaseworkEditor"

const mutations = vi.hoisted(() => ({
  create: vi.fn(),
  update: vi.fn(),
  confidence: vi.fn(),
  significance: vi.fn(),
  get: vi.fn(),
  value: vi.fn(),
}))

vi.mock("../casework-api", () => ({
  caseworkAPI: { get: (...args: unknown[]) => mutations.get(...args) },
}))

vi.mock("../hooks/use-casework", () => ({
  useCreateCaseworkEntry: () => ({
    mutateAsync: mutations.create,
    isPending: false,
  }),
  useUpdateCaseworkEntry: () => ({
    mutateAsync: mutations.update,
    isPending: false,
  }),
  useChangeCaseworkConfidence: () => ({
    mutateAsync: mutations.confidence,
    isPending: false,
  }),
  useChangeCaseworkSignificance: () => ({
    mutateAsync: mutations.significance,
    isPending: false,
  }),
}))

vi.mock("./CaseworkComposer", () => ({
  CaseworkComposer: ({ onSubmit }: { onSubmit: (value: unknown) => void }) => (
    <button type="button" onClick={() => onSubmit(mutations.value())}>
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
    mutations.value.mockReturnValue({
      entry_type: "note",
      title: null,
      body: "Concurrent draft",
      tags: [],
      significance: null,
      confidence: null,
      confidence_rationale: null,
      links: [],
    })
    mutations.get.mockResolvedValue(entry)
  })

  it("retains the draft and reports an optimistic concurrency conflict", async () => {
    mutations.update.mockRejectedValue(
      new ApiError("Entry was updated by another investigator", 409)
    )
    const onReload = vi.fn()
    render(
      <CaseworkEditor
        caseId="case-1"
        entry={entry}
        canEdit
        onReload={onReload}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: "Save fixture" }))

    expect(
      await screen.findByText("This entry changed while you were editing.")
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Save fixture" })
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Reload" }))
    await waitFor(() =>
      expect(
        screen.queryByText("This entry changed while you were editing.")
      ).not.toBeInTheDocument()
    )
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

  it("retries a partially saved assessment using the saved content version", async () => {
    const finding: CaseworkEntry = {
      ...entry,
      entry_type: "finding",
      title: "A supported conclusion",
      significance: "low",
    }
    mutations.value.mockReturnValue({
      entry_type: "finding",
      title: finding.title,
      body: "Revised reasoning",
      tags: [],
      significance: "high",
      confidence: null,
      confidence_rationale: null,
      links: [],
    })
    mutations.update
      .mockResolvedValueOnce({
        ...finding,
        body: "Revised reasoning",
        version: 3,
      })
      .mockResolvedValueOnce({
        ...finding,
        body: "Revised reasoning",
        version: 4,
      })
    mutations.significance
      .mockRejectedValueOnce(new Error("Connection interrupted"))
      .mockResolvedValueOnce({
        ...finding,
        significance: "high",
        body: "Revised reasoning",
        version: 5,
      })
    const onSaved = vi.fn()
    render(
      <CaseworkEditor
        caseId="case-1"
        entry={finding}
        canEdit
        onSaved={onSaved}
      />
    )
    fireEvent.click(screen.getByRole("button", { name: "Save fixture" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your text and links were saved, but the assessment could not be updated"
    )
    expect(onSaved).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "Save fixture" }))
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
    expect(
      mutations.update.mock.calls.map((call) => call[0].input.expected_version)
    ).toEqual([2, 3])
    expect(
      mutations.significance.mock.calls.map((call) => call[0].version)
    ).toEqual([3, 4])
    expect(onSaved.mock.calls[0][0]).toMatchObject({
      significance: "high",
      version: 5,
    })
  })

  it("prevents a second save while the first write is still pending", async () => {
    let resolveSave: (value: CaseworkEntry) => void = () => {}
    mutations.update.mockReturnValue(
      new Promise<CaseworkEntry>((resolve) => {
        resolveSave = resolve
      })
    )
    const onSaved = vi.fn()
    render(
      <CaseworkEditor caseId="case-1" entry={entry} canEdit onSaved={onSaved} />
    )
    fireEvent.click(screen.getByRole("button", { name: "Save fixture" }))
    fireEvent.click(screen.getByRole("button", { name: "Save fixture" }))
    expect(mutations.update).toHaveBeenCalledOnce()
    resolveSave({ ...entry, version: 3 })
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
  })
})
