import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { CaseworkEntry } from "../casework-api"
import { CaseworkDetailSheet } from "./CaseworkDetailSheet"
import "@/styles/globals.css"
import { page } from "vitest/browser"

const browserHooks = vi.hoisted(() => ({
  entry: vi.fn(),
  lifecycle: vi.fn(),
  convert: vi.fn(),
  remove: vi.fn(),
  restore: vi.fn(),
}))

vi.mock("../hooks/use-casework", () => ({
  useCaseworkEntry: () => browserHooks.entry(),
  useChangeCaseworkLifecycle: () => ({ mutateAsync: browserHooks.lifecycle, isPending: false }),
  useConvertTheory: () => ({ mutateAsync: browserHooks.convert, isPending: false }),
  useDeleteCaseworkEntry: () => ({ mutateAsync: browserHooks.remove, isPending: false }),
  useRestoreCaseworkEntry: () => ({ mutateAsync: browserHooks.restore, isPending: false }),
  useCreateCaseworkEntry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateCaseworkEntry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useChangeCaseworkConfidence: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useChangeCaseworkSignificance: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAttachmentOptions: () => ({ data: { items: [] }, isLoading: false }),
}))
vi.mock("../hooks/use-current-casework-links", () => ({
  useCurrentCaseworkLinks: () => [],
}))
vi.mock("@/features/workspace-ai/components/WorkspaceAIPanel", () => ({
  WorkspaceAIPanel: () => <div>Cited AI assistance</div>,
}))

const theory: CaseworkEntry = {
  id: "theory-browser-1",
  case_id: "case-browser",
  entry_type: "theory",
  title: "Coordinated asset disposal",
  body: "The timing may show coordination.",
  tags: ["assets"],
  lifecycle_state: "investigating",
  significance: null,
  confidence: 55,
  confidence_rationale: "Two independent records align.",
  review_state: "accepted",
  version: 4,
  migration_metadata: {},
  needs_migration_review: false,
  links: [],
  revisions: [
    {
      id: "revision-1",
      entry_id: "theory-browser-1",
      revision_number: 1,
      entry_type: "theory",
      title: "Coordinated asset disposal",
      body: "Initial version",
      tags: [],
      lifecycle_state: "proposed",
      significance: null,
      confidence: 30,
      confidence_rationale: null,
      review_state: "accepted",
      editor_name: "Alex Morgan",
      created_at: "2026-08-30T10:00:00Z",
    },
  ],
  events: [],
}

function renderSheet() {
  return render(
    <MemoryRouter>
      <CaseworkDetailSheet
        caseId="case-browser"
        entryId={theory.id}
        open
        canEdit
        onOpenChange={vi.fn()}
        onOpenEntry={vi.fn()}
      />
    </MemoryRouter>,
  )
}

describe("casework detail in Chromium", () => {
  it("shows only three revisions at a time when history is expanded", async () => {
    await page.viewport(1280, 900)
    browserHooks.entry.mockReturnValue({ data: { ...theory, revisions: Array.from({ length: 7 }, (_, index) => ({ ...theory.revisions![0], id: `revision-${index}`, revision_number: index + 1 })) }, isLoading: false })
    renderSheet()
    expect(screen.getByText("Version 7")).not.toBeVisible()
    fireEvent.click(screen.getByText(/Revision history/))
    expect(screen.getByText("Version 7")).toBeVisible()
    expect(screen.queryByText("Version 4")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Next" }))
    expect(screen.getByText("Version 4")).toBeVisible()
    expect(screen.queryByText("Version 7")).not.toBeInTheDocument()
    expect(screen.getByText("Page 2 of 3")).toBeVisible()
    await page.screenshot({ path: "../../../../../output/workspace-history.png" })
  })
  beforeEach(() => {
    Object.values(browserHooks).forEach((mock) => mock.mockReset())
    browserHooks.entry.mockReturnValue({
      data: theory,
      isLoading: false,
      isError: false,
      refetch: vi.fn().mockResolvedValue({ data: theory }),
    })
    browserHooks.convert.mockResolvedValue({
      theory: { ...theory, lifecycle_state: "converted" },
      finding: { ...theory, id: "finding-browser-1", entry_type: "finding" },
    })
  })

  it("shows immutable history and converts an editable theory draft", async () => {
    renderSheet()

    expect(screen.getByText(/Revision history/)).toBeVisible()
    expect(screen.getByText("Version 1")).not.toBeVisible()
    fireEvent.click(screen.getByText(/Revision history/))
    expect(screen.getByText("Version 1")).toBeVisible()
    fireEvent.click(screen.getByRole("button", { name: "Convert to finding" }))
    const title = await screen.findByLabelText("Finding title")
    fireEvent.change(title, { target: { value: "Established coordinated disposal" } })
    fireEvent.click(screen.getByRole("button", { name: "Create finding" }))

    await waitFor(() =>
      expect(browserHooks.convert).toHaveBeenCalledWith({
        entryId: theory.id,
        version: 4,
        significance: "medium",
        draft: {
          title: "Established coordinated disposal",
          body: theory.body,
        },
      }),
    )
  })

  it("restores soft-deleted casework", async () => {
    browserHooks.entry.mockReturnValue({
      data: { ...theory, deleted_at: "2026-09-01T12:00:00Z" },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    })
    browserHooks.restore.mockResolvedValue({ ...theory, version: 5 })
    renderSheet()

    fireEvent.click(screen.getByRole("button", { name: "Restore" }))
    await waitFor(() =>
      expect(browserHooks.restore).toHaveBeenCalledWith({
        entryId: theory.id,
        version: 4,
      }),
    )
  })
})
