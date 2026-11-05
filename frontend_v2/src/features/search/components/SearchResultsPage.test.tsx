import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

const api = vi.hoisted(() => ({ searchGroup: vi.fn(), freeze: vi.fn(), targets: vi.fn(), add: vi.fn(), undo: vi.fn(), canEdit: { value: true } }))
vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), searchGroup: api.searchGroup, freezeSearchGroup: api.freeze }))
vi.mock("@/features/cases/hooks/use-cases", () => ({ useCase: () => ({ data: { id: "c1" } }) }))
vi.mock("@/features/cases/hooks/use-case-permissions", () => ({ useCasePermissions: () => ({ canEdit: api.canEdit.value }) }))
vi.mock("@/features/phones/hooks/use-collect", () => ({ useCollectTargets: () => ({ data: api.targets() }) }))
vi.mock("@/features/phones/collect.api", async (orig) => ({
  ...(await orig<typeof import("@/features/phones/collect.api")>()),
  liveCollectClient: { add: api.add },
  undoCollect: api.undo,
}))
vi.mock("./SearchDialog", () => ({ HitLine: ({ hit }: { hit: { title: string } }) => <span>{hit.title}</span>, PaymentTotalsLine: () => null }))
import { SearchResultsPage } from "./SearchResultsPage"

/** 07 J-5, 6.1, 6.2: a hit or the whole result goes to a container, with counts and Undo. Invented data only. */
const hit = (n: number, extra = {}) => ({
  kind: "message", title: `Hit ${n}`, snippet: null, record_uid: `r${n}`, evidence_file_id: null, open: { screen: "conversations", params: { phone: "e1", thread: "t" } }, ...extra,
})
const page = (items: unknown[], total = items.length) => ({ group: "messages", total, items, next_cursor: null, complete: true, limits: [] })

function open(group = "messages") {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[`/cases/c1/search?q=blue&group=${group}`]}>
        <Routes><Route path="/cases/:id/search" element={<SearchResultsPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.canEdit.value = true
  api.targets.mockReturnValue([{ kind: "finding", id: "f1", label: "Finding one" }, { kind: "dossier", id: "d1", label: "Ana" }])
  api.add.mockResolvedValue({ added: 2, skipped: 1, refused: 0, linkIds: ["l1", "l2"] })
  api.undo.mockResolvedValue(2)
})

describe("Add to… on Search results", () => {
  it("adds the chosen hits and reports added and already-there, with Undo", async () => {
    api.searchGroup.mockResolvedValue(page([hit(1), hit(2), hit(3)]))
    const user = userEvent.setup()
    open()
    await user.click(await screen.findByRole("checkbox", { name: "Choose Hit 1" }))
    await user.click(screen.getByRole("checkbox", { name: "Choose Hit 3" }))
    await user.click(screen.getByRole("button", { name: "Add to…" }))
    await user.click(await screen.findByRole("button", { name: /Finding or theory/ }))
    await user.click(screen.getByRole("option", { name: /Finding one/ }))
    await waitFor(() => expect(api.add).toHaveBeenCalled())
    const [, , links, opts] = api.add.mock.calls[0]
    expect(links.map((l: { target_id: string }) => l.target_id)).toEqual(["r1", "r3"])
    expect(links[0]).toMatchObject({ target_type: "phone_record", source_anchor: { origin: "search", query: "blue", extraction_id: "e1" } })
    expect(opts.origin).toBe("Added from Search")
    expect(await screen.findByText(/Added 2 messages to Finding one\. 1 was already there\./)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Undo" }))
    expect(await screen.findByText("Removed 2 links that add made.")).toBeInTheDocument()
  })

  it("keeps a whole result past 500 as one selection and states its counts and what is left out", async () => {
    api.searchGroup.mockResolvedValue(page(Array.from({ length: 501 }, (_, i) => hit(i))))
    api.freeze.mockResolvedValue({ id: "s1", record_count: 540, event_count: 501, words: "Every message", group_total: 503, left_out: 2 })
    const user = userEvent.setup()
    open()
    await user.click(await screen.findByRole("checkbox", { name: "Every hit (501)" }))
    await waitFor(() => expect(api.freeze).toHaveBeenCalledWith("c1", "blue", "messages", false, []))
    expect(await screen.findByText(/All 501 messages \(540 records, every copy included\) will be added as one selection\. 2 of the 503 hits have no phone record behind them and are left out\./)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Add to…" }))
    expect(await screen.findByRole("heading", { name: /Add 1 selection to/ })).toBeInTheDocument()
  })

  it("does not freeze anything until every hit is chosen", async () => {
    api.searchGroup.mockResolvedValue(page(Array.from({ length: 501 }, (_, i) => hit(i))))
    open()
    await screen.findByRole("checkbox", { name: "Every hit (501)" })
    expect(api.freeze).not.toHaveBeenCalled()
  })

  it("states a hit with nothing to save and takes it out of the add", async () => {
    api.searchGroup.mockResolvedValue(page([hit(1), hit(2, { record_uid: null })]))
    const user = userEvent.setup()
    open()
    await user.click(await screen.findByRole("checkbox", { name: "Every hit (2)" }))
    expect(screen.getByText(/1 of the hits chosen has nothing that can be saved and will be left out\./)).toBeInTheDocument()
  })

  it("people reach a dossier only through a link decision", async () => {
    api.searchGroup.mockResolvedValue(page([hit(1, { record_uid: null, identity_key: "phone:+1" })]))
    const user = userEvent.setup()
    open("people")
    await user.click(await screen.findByRole("checkbox", { name: "Every hit (1)" }))
    await user.click(screen.getByRole("button", { name: "Add to…" }))
    await user.click(await screen.findByRole("button", { name: /Dossier/ }))
    expect(screen.getByText(/through a link decision in Phone identities/)).toBeInTheDocument()
    expect(screen.queryByRole("option", { name: /Ana/ })).not.toBeInTheDocument()
  })

  it("says who may add when the person may not", async () => {
    api.canEdit.value = false
    api.searchGroup.mockResolvedValue(page([hit(1)]))
    open()
    expect(await screen.findByText("A case member who can edit can add.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Add to…" })).toBeDisabled()
  })
})
