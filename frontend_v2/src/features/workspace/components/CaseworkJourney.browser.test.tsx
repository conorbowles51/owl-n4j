import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { MemoryRouter, useLocation } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { ApiError } from "@/lib/api-client"
import type {
  CaseworkEntry,
  CaseworkLinkInput,
  CaseworkListParams,
} from "../casework-api"
import { CaseworkListView } from "./CaseworkListView"
import "@/styles/globals.css"

const state = vi.hoisted(() => ({
  entries: [] as CaseworkEntry[],
  update: vi.fn(),
  create: vi.fn(),
  get: vi.fn(),
  failList: false,
  retry: vi.fn(),
}))
vi.mock("../casework-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../casework-api")>()
  return {
    ...actual,
    caseworkAPI: {
      ...actual.caseworkAPI,
      get: (...args: unknown[]) => state.get(...args),
    },
  }
})
vi.mock("../hooks/use-casework", () => {
  const mutation = () => ({ mutateAsync: vi.fn(), isPending: false })
  return {
    useCaseworkEntries: (_caseId: string, params: CaseworkListParams) => {
      const entries = state.entries.filter(
        (entry) =>
          (!params.entry_type || params.entry_type === entry.entry_type) &&
          (!params.q ||
            `${entry.title} ${entry.body}`
              .toLowerCase()
              .includes(params.q.toLowerCase()))
      )
      return {
        data: { entries, total: entries.length },
        isLoading: false,
        isError: state.failList,
        refetch: state.retry,
      }
    },
    useCaseworkAuthors: () => ({
      data: [{ user_id: "author-1", label: "Alex Morgan" }],
    }),
    useCaseworkEntry: (_caseId: string, id: string) => ({
      data: state.entries.find((entry) => entry.id === id),
      isLoading: false,
      refetch: () =>
        Promise.resolve({
          data: state.entries.find((entry) => entry.id === id),
        }),
    }),
    useCreateCaseworkEntry: () => ({
      mutateAsync: state.create,
      isPending: false,
    }),
    useUpdateCaseworkEntry: () => ({
      mutateAsync: state.update,
      isPending: false,
    }),
    useChangeCaseworkConfidence: mutation,
    useChangeCaseworkSignificance: mutation,
    useChangeCaseworkLifecycle: mutation,
    useConvertTheory: mutation,
    useDeleteCaseworkEntry: mutation,
    useRestoreCaseworkEntry: mutation,
  }
})
vi.mock("../hooks/use-current-casework-links", () => ({
  useCurrentCaseworkLinks: () => [],
}))
vi.mock("@/features/phones/link-states", () => ({
  useLinkStates: () => ({}),
  useLinkChoice: () => ({ isPending: false }),
}))
vi.mock("@/features/dossiers/hooks", () => ({
  useDossiers: ({ linkedEntryId }: { linkedEntryId?: string }) => ({
    data: {
      dossiers:
        linkedEntryId === "finding-1"
          ? [
              {
                id: "dossier-1",
                display_name: "Northbank Holdings",
                archived_at: null,
              },
            ]
          : [],
      total: linkedEntryId === "finding-1" ? 1 : 0,
    },
  }),
}))
vi.mock("@/features/dossiers/components/DossierDetailSheet", () => ({
  DossierDetailSheet: ({
    onOpenChange,
  }: {
    onOpenChange: (open: boolean) => void
  }) => (
    <div role="dialog" aria-label="Northbank dossier">
      <p>Northbank Holdings dossier</p>
      <button onClick={() => onOpenChange(false)}>Back to casework</button>
    </div>
  ),
}))
vi.mock("./CaseworkAttachmentPicker", () => ({
  CaseworkAttachmentPicker: ({
    onAttach,
  }: {
    onAttach: (link: CaseworkLinkInput) => void
  }) => (
    <div>
      <button
        onClick={() =>
          onAttach({
            target_type: "task",
            target_id: "task-browser",
            target_label: "Contact the witness",
            relationship: "context",
          })
        }
      >
        Attach task
      </button>
      <button
        onClick={() =>
          onAttach({
            target_type: "deadline",
            target_id: "deadline-browser",
            target_label: "Review date",
            relationship: "context",
          })
        }
      >
        Attach deadline
      </button>
    </div>
  ),
}))

const base: CaseworkEntry = {
  id: "note-1",
  case_id: "case-demo",
  entry_type: "note",
  title: "A second address in the correspondence",
  body: "The correspondence refers to a second office. Check the lease records before adding it to the timeline.",
  tags: ["follow-up"],
  version: 1,
  review_state: "accepted",
  migration_metadata: {},
  needs_migration_review: false,
  links: [],
  author_name: "Alex Morgan",
  updated_at: "2026-11-10T10:30:00Z",
}

function LocationProbe() {
  const location = useLocation()
  return (
    <output hidden data-testid="casework-route">
      {location.pathname + location.search}
    </output>
  )
}

function mount(canEdit = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const element = (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <LocationProbe />
        <main className="mx-auto max-w-5xl p-5 sm:p-8">
          <CaseworkListView caseId="case-demo" canEdit={canEdit} />
        </main>
      </MemoryRouter>
    </QueryClientProvider>
  )
  const view = render(element)
  return {
    ...view,
    refresh: () =>
      view.rerender(
        <QueryClientProvider client={client}>
          <MemoryRouter>
            <LocationProbe />
            <main className="mx-auto max-w-5xl p-5 sm:p-8">
              <CaseworkListView caseId="case-demo" canEdit={canEdit} />
            </main>
          </MemoryRouter>
        </QueryClientProvider>
      ),
  }
}

describe("Connected casework journeys", () => {
  beforeEach(() => {
    state.failList = false
    state.entries = [
      { ...base },
      {
        ...base,
        id: "finding-1",
        entry_type: "finding",
        title: "The company continued operating after the notice",
        body: "Three dated records place the business at the same address after the notice was served.",
        lifecycle_state: "active",
        significance: "high",
        tags: ["operations"],
        links: [
          {
            id: "link-1",
            entry_id: "finding-1",
            case_id: "case-demo",
            target_type: "evidence",
            target_id: "evidence-1",
            target_label: "Correspondence.pdf",
            relationship: "supports",
            source_anchor: { page: 4 },
            metadata: {},
          },
        ],
      },
      {
        ...base,
        id: "theory-1",
        entry_type: "theory",
        title: "A common decision maker connects the two companies",
        body: "The same contact appears in both sets of records. Compare the interviews before drawing a conclusion.",
        lifecycle_state: "investigating",
        confidence: 55,
        tags: [],
        links: [],
      },
    ]
    state.get
      .mockReset()
      .mockImplementation((_caseId, id) =>
        Promise.resolve(state.entries.find((entry) => entry.id === id))
      )
    state.update.mockReset().mockImplementation(({ entryId, input }) => {
      const index = state.entries.findIndex((entry) => entry.id === entryId)
      if (state.entries[index].version !== input.expected_version)
        return Promise.reject(
          new ApiError("Another investigator saved a newer version.", 409)
        )
      state.entries[index] = {
        ...state.entries[index],
        ...input,
        version: input.expected_version + 1,
      }
      return Promise.resolve(state.entries[index])
    })
    state.create.mockReset().mockImplementation((input) => {
      const entry = {
        ...base,
        ...input,
        id: "new-note",
        links: (input.links ?? []).map(
          (link: CaseworkLinkInput, index: number) => ({
            ...link,
            id: `new-link-${index}`,
            entry_id: "new-note",
            case_id: "case-demo",
          })
        ),
      }
      state.entries = [entry, ...state.entries]
      return Promise.resolve(entry)
    })
  })

  it("browses all work, filters it, creates a note and reopens it", async () => {
    await page.viewport(1440, 1000)
    mount()
    expect(
      screen.getByText("A second address in the correspondence")
    ).toBeVisible()
    expect(
      screen.getByText("A common decision maker connects the two companies")
    ).toBeVisible()
    await page.screenshot({
      path: "../../../../../output/workspace-redesign/casework-desktop.png",
    })
    document.documentElement.classList.add("dark")
    await page.screenshot({
      path: "../../../../../output/workspace-redesign/casework-dark.png",
    })
    document.documentElement.classList.remove("dark")
    await page.getByRole("button", { name: "Theories", exact: true }).click()
    expect(
      screen.queryByText("A second address in the correspondence")
    ).not.toBeInTheDocument()
    await page
      .getByRole("button", { name: "All casework", exact: true })
      .click()
    await page
      .getByRole("button", { name: "New casework", exact: true })
      .click()
    fireEvent.change(screen.getByLabelText(/^Title/), {
      target: { value: "Follow up on the address" },
    })
    fireEvent.change(screen.getByLabelText("Casework"), {
      target: { value: "Ask for the office lease and compare the dates." },
    })
    await page.getByRole("button", { name: "Save note", exact: true }).click()
    await waitFor(() => expect(state.create).toHaveBeenCalledOnce())
    expect(
      await screen.findByRole("heading", { name: "Follow up on the address" })
    ).toBeVisible()
    await page.getByRole("button", { name: "Close", exact: true }).click()
    await page.getByRole("button", { name: /Follow up on the address/ }).click()
    expect(
      screen.getByRole("heading", { name: "Follow up on the address" })
    ).toBeVisible()
  })

  it("preserves an edited draft during background refresh and explicitly reloads a conflict", async () => {
    await page.viewport(1280, 900)
    const view = mount()
    await page
      .getByRole("button", { name: /The company continued operating/ })
      .click()
    expect(
      screen.getByRole("button", { name: "Northbank Holdings" })
    ).toBeVisible()
    await page.screenshot({
      path: "../../../../../output/workspace-redesign/casework-detail.png",
    })
    await page.getByRole("button", { name: "Edit", exact: true }).click()
    fireEvent.change(screen.getByLabelText("Casework"), {
      target: { value: "My unsaved reasoning remains intact." },
    })
    state.entries[1] = {
      ...state.entries[1],
      body: "Another investigator added a source.",
      version: 2,
    }
    view.refresh()
    expect(screen.getByLabelText("Casework")).toHaveValue(
      "My unsaved reasoning remains intact."
    )
    await page
      .getByRole("button", { name: "Save changes", exact: true })
      .click()
    expect(
      await screen.findByText("This entry changed while you were editing.")
    ).toBeVisible()
    expect(screen.getByLabelText("Casework")).toHaveValue(
      "My unsaved reasoning remains intact."
    )
    await page.getByRole("button", { name: "Reload", exact: true }).click()
    await waitFor(() =>
      expect(screen.getByLabelText("Casework")).toHaveValue(
        "Another investigator added a source."
      )
    )
    fireEvent.change(screen.getByLabelText("Casework"), {
      target: { value: "Reconciled reasoning with the new source." },
    })
    await page
      .getByRole("button", { name: "Save changes", exact: true })
      .click()
    await waitFor(() =>
      expect(screen.queryByLabelText("Casework")).not.toBeInTheDocument()
    )
    expect(
      screen.getByText("Reconciled reasoning with the new source.")
    ).toBeVisible()
    expect(state.update.mock.calls.at(-1)?.[0].input.expected_version).toBe(2)
  })

  it("keeps mobile browsing and dossier return usable for viewers", async () => {
    await page.viewport(390, 844)
    mount(false)
    expect(
      screen.queryByRole("button", { name: "New casework" })
    ).not.toBeInTheDocument()
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(390)
    await page.screenshot({
      path: "../../../../../output/workspace-redesign/casework-mobile.png",
    })
    await page
      .getByRole("button", { name: /The company continued operating/ })
      .click()
    expect(
      screen.queryByRole("button", { name: "Edit" })
    ).not.toBeInTheDocument()
    await page
      .getByRole("button", { name: "Northbank Holdings", exact: true })
      .click()
    const dossier = await screen.findByRole("dialog", {
      name: "Northbank dossier",
    })
    fireEvent.click(
      within(dossier).getByRole("button", { name: "Back to casework" })
    )
    expect(
      screen.getByRole("heading", {
        name: "The company continued operating after the notice",
      })
    ).toBeVisible()
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(390)
  })

  it("keeps a new note intact after a failed save and lets the investigator retry", async () => {
    await page.viewport(390, 844)
    state.create.mockRejectedValueOnce(
      new Error("Connection interrupted. Try again.")
    )
    mount()
    await page
      .getByRole("button", { name: "New casework", exact: true })
      .click()
    fireEvent.change(screen.getByLabelText("Casework"), {
      target: { value: "Keep this observation until the connection returns." },
    })
    await page.getByRole("button", { name: "Save note", exact: true }).click()
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Connection interrupted"
    )
    expect(screen.getByLabelText("Casework")).toHaveValue(
      "Keep this observation until the connection returns."
    )
    expect(screen.getByRole("button", { name: "Save note" })).toBeEnabled()
    await page.getByRole("button", { name: "Save note", exact: true }).click()
    expect(
      await screen.findByRole("heading", {
        name: "Keep this observation until the connection returns.",
      })
    ).toBeVisible()
    expect(state.create).toHaveBeenCalledTimes(2)
  })

  it.each([
    ["task", "Contact the witness", "task-browser"],
    ["deadline", "Review date", "deadline-browser"],
  ])(
    "saves a note with a linked %s and opens that exact work item",
    async (type, label, id) => {
      await page.viewport(1280, 900)
      mount()
      await page
        .getByRole("button", { name: "New casework", exact: true })
        .click()
      fireEvent.change(screen.getByLabelText("Casework"), {
        target: { value: "Follow up before the review date." },
      })
      await page.getByRole("button", { name: "Search", exact: true }).click()
      await page
        .getByRole("button", { name: `Attach ${type}`, exact: true })
        .click()
      await page.getByRole("button", { name: "Save note", exact: true }).click()
      expect(
        await screen.findByRole("heading", {
          name: "Follow up before the review date.",
        })
      ).toBeVisible()
      const linked = page.getByRole("button", { name: new RegExp(label) })
      await linked.click()
      expect(screen.getByTestId("casework-route")).toHaveTextContent(
        `/cases/case-demo/workspace?view=work&item=${id}`
      )
      expect(state.create.mock.calls[0][0].links).toEqual([
        expect.objectContaining({ target_type: type, target_id: id }),
      ])
    }
  )
})
