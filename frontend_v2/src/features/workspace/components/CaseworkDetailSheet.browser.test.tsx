import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter, MemoryRouter, useLocation } from "react-router-dom"
import { initializeUnsavedHistoryGuard } from "@/hooks/use-unsaved-history-guard"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
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
  useChangeCaseworkLifecycle: () => ({
    mutateAsync: browserHooks.lifecycle,
    isPending: false,
  }),
  useConvertTheory: () => ({
    mutateAsync: browserHooks.convert,
    isPending: false,
  }),
  useDeleteCaseworkEntry: () => ({
    mutateAsync: browserHooks.remove,
    isPending: false,
  }),
  useRestoreCaseworkEntry: () => ({
    mutateAsync: browserHooks.restore,
    isPending: false,
  }),
  useCreateCaseworkEntry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateCaseworkEntry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useChangeCaseworkConfidence: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
  useChangeCaseworkSignificance: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
  useAttachmentOptions: () => ({ data: { items: [] }, isLoading: false }),
}))
vi.mock("../hooks/use-current-casework-links", () => ({
  useCurrentCaseworkLinks: () => [],
}))
vi.mock("@/features/dossiers/hooks", () => ({
  useDossiers: () => ({ data: { dossiers: [], total: 0 } }),
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
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <CaseworkDetailSheet
          caseId="case-browser"
          entryId={theory.id}
          open
          canEdit
          onOpenChange={vi.fn()}
          onOpenEntry={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

function HistoryCasework() {
  const location = useLocation()
  return new URLSearchParams(location.search).get("casework-step") ===
    "edit" ? (
    <CaseworkDetailSheet
      caseId="case-browser"
      entryId={theory.id}
      open
      canEdit
      onOpenChange={vi.fn()}
    />
  ) : (
    <h1>Casework home</h1>
  )
}

describe("casework detail in Chromium", () => {
  afterEach(() => vi.restoreAllMocks())
  it("shows only three revisions at a time when history is expanded", async () => {
    await page.viewport(1280, 900)
    browserHooks.entry.mockReturnValue({
      data: {
        ...theory,
        revisions: Array.from({ length: 7 }, (_, index) => ({
          ...theory.revisions![0],
          id: `revision-${index}`,
          revision_number: index + 1,
        })),
      },
      isLoading: false,
    })
    renderSheet()
    expect(screen.getByText("Version 7")).not.toBeVisible()
    fireEvent.click(screen.getByText(/Revision history/))
    expect(screen.getByText("Version 7")).toBeVisible()
    expect(screen.queryByText("Version 4")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Next" }))
    expect(screen.getByText("Version 4")).toBeVisible()
    expect(screen.queryByText("Version 7")).not.toBeInTheDocument()
    expect(screen.getByText("Page 2 of 3")).toBeVisible()
    await page.screenshot({
      path: "../../../../../output/workspace-history.png",
    })
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
    fireEvent.change(title, {
      target: { value: "Established coordinated disposal" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Create finding" }))

    await waitFor(() =>
      expect(browserHooks.convert).toHaveBeenCalledWith({
        entryId: theory.id,
        version: 4,
        significance: null,
        draft: {
          title: "Established coordinated disposal",
          body: theory.body,
        },
      })
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
      })
    )
  })

  it("preserves a rewritten conversion draft when Escape, outside dismissal or Cancel is declined", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    renderSheet()
    fireEvent.click(screen.getByRole("button", { name: "Convert to finding" }))
    const dialog = screen.getByRole("dialog", {
      name: "Create finding from theory",
    })
    fireEvent.change(screen.getByLabelText("Finding title"), {
      target: { value: "Reviewed finding title" },
    })
    fireEvent.change(screen.getByLabelText("Finding"), {
      target: { value: "My rewritten conclusion, with supporting details." },
    })
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }))
    expect(confirm).toHaveBeenCalledWith("Discard your unsaved finding draft?")
    expect(screen.getByLabelText("Finding")).toHaveValue(
      "My rewritten conclusion, with supporting details."
    )
    confirm.mockClear()
    fireEvent.keyDown(document, { key: "Escape" })
    expect(confirm).toHaveBeenCalledOnce()
    expect(screen.getByLabelText("Finding title")).toHaveValue(
      "Reviewed finding title"
    )
    confirm.mockClear()
    const overlays = document.querySelectorAll('[data-slot="dialog-overlay"]')
    await act(async () =>
      page
        .elementLocator(overlays[overlays.length - 1])
        .click({ position: { x: 8, y: 8 } })
    )
    await waitFor(() => expect(confirm).toHaveBeenCalledOnce(), {
      timeout: 1000,
    })
    expect(screen.getByLabelText("Finding")).toHaveValue(
      "My rewritten conclusion, with supporting details."
    )
    const unload = new Event("beforeunload", { cancelable: true })
    window.dispatchEvent(unload)
    expect(unload.defaultPrevented).toBe(true)
    confirm.mockReturnValue(true)
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }))
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Create finding from theory" })
      ).not.toBeInTheDocument()
    )
  })

  it("holds the conversion dialog open while saving and preserves the draft after failure", async () => {
    let rejectSave: (error: Error) => void = () => {}
    browserHooks.convert.mockReturnValueOnce(
      new Promise((_resolve, reject) => {
        rejectSave = reject
      })
    )
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true)
    renderSheet()
    fireEvent.click(screen.getByRole("button", { name: "Convert to finding" }))
    fireEvent.change(screen.getByLabelText("Finding"), {
      target: { value: "A carefully rewritten finding." },
    })
    fireEvent.click(screen.getByRole("button", { name: "Create finding" }))
    const dialog = screen.getByRole("dialog", {
      name: "Create finding from theory",
    })
    expect(
      within(dialog).getByRole("button", { name: "Cancel" })
    ).toBeDisabled()
    fireEvent.keyDown(document, { key: "Escape" })
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }))
    expect(
      screen.getByRole("dialog", { name: "Create finding from theory" })
    ).toBeVisible()
    expect(confirm).not.toHaveBeenCalled()
    await act(async () =>
      rejectSave(new Error("The connection was interrupted."))
    )
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The connection was interrupted."
    )
    expect(screen.getByLabelText("Finding")).toHaveValue(
      "A carefully rewritten finding."
    )
    fireEvent.click(screen.getByRole("button", { name: "Create finding" }))
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Create finding from theory" })
      ).not.toBeInTheDocument()
    )
    expect(browserHooks.convert).toHaveBeenCalledTimes(2)
    expect(confirm).not.toHaveBeenCalled()
  })

  it("keeps status and rationale changes through declined dismissal and a failed save", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    browserHooks.lifecycle
      .mockRejectedValueOnce(new Error("Try again when connected."))
      .mockResolvedValueOnce({
        ...theory,
        lifecycle_state: "weakened",
        version: 5,
      })
    renderSheet()
    fireEvent.click(screen.getByRole("button", { name: "Change lifecycle" }))
    fireEvent.click(screen.getByRole("combobox", { name: "Status" }))
    fireEvent.click(await screen.findByRole("option", { name: "Weakened" }))
    fireEvent.change(screen.getByLabelText("Rationale (optional)"), {
      target: { value: "The new interview challenges the chronology." },
    })
    const dialog = screen.getByRole("dialog", { name: "Change lifecycle" })
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }))
    expect(confirm).toHaveBeenCalledWith("Discard your unsaved status changes?")
    fireEvent.keyDown(document, { key: "Escape" })
    expect(screen.getByLabelText("Rationale (optional)")).toHaveValue(
      "The new interview challenges the chronology."
    )
    const unload = new Event("beforeunload", { cancelable: true })
    window.dispatchEvent(unload)
    expect(unload.defaultPrevented).toBe(true)
    fireEvent.click(screen.getByRole("button", { name: "Save lifecycle" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Try again when connected."
    )
    expect(screen.getByLabelText("Rationale (optional)")).toHaveValue(
      "The new interview challenges the chronology."
    )
    fireEvent.click(screen.getByRole("button", { name: "Save lifecycle" }))
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Change lifecycle" })
      ).not.toBeInTheDocument()
    )
    expect(browserHooks.lifecycle.mock.calls.at(-1)?.[0]).toMatchObject({
      state: "weakened",
      rationale: "The new interview challenges the chronology.",
      version: 4,
    })
  })

  it.each(["conversion", "lifecycle"])(
    "protects the %s draft from browser Back",
    async (kind) => {
      const originalUrl = window.location.href
      const originalState = window.history.state
      initializeUnsavedHistoryGuard()
      window.history.replaceState({ idx: 0 }, "", "?casework-step=home")
      window.history.pushState({ idx: 1 }, "", "?casework-step=edit")
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
      const view = render(
        <QueryClientProvider
          client={
            new QueryClient({ defaultOptions: { queries: { retry: false } } })
          }
        >
          <BrowserRouter>
            <HistoryCasework />
          </BrowserRouter>
        </QueryClientProvider>
      )
      try {
        fireEvent.click(
          screen.getByRole("button", {
            name:
              kind === "conversion" ? "Convert to finding" : "Change lifecycle",
          })
        )
        const label = kind === "conversion" ? "Finding" : "Rationale (optional)"
        fireEvent.change(screen.getByLabelText(label), {
          target: { value: "Keep my investigative reasoning." },
        })
        act(() => window.history.back())
        await waitFor(() => expect(confirm).toHaveBeenCalledOnce(), {
          timeout: 2500,
        })
        await waitFor(() => expect(window.history.state.idx).toBe(1), {
          timeout: 2500,
        })
        expect(screen.getByLabelText(label)).toHaveValue(
          "Keep my investigative reasoning."
        )
        confirm.mockReturnValue(true)
        act(() => window.history.back())
        expect(
          await screen.findByRole(
            "heading",
            { name: "Casework home" },
            { timeout: 2500 }
          )
        ).toBeVisible()
      } finally {
        view.unmount()
        window.history.replaceState(originalState, "", originalUrl)
      }
    }
  )
})
