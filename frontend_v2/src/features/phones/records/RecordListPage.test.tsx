import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { RecordListPage } from "./RecordListPage"
import { recordListFilter, recordListHref } from "./record-list-url"

const mocks = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock("../api", () => ({
  getRecordList: mocks.list,
  failureText: (_e: unknown, w: string) => w,
}))
vi.mock("../hooks/use-collect", () => ({ useCollectTargets: () => ({ data: [] }) }))
vi.mock("../phones-query", () => ({ phonesQuery: () => ({ queryKey: ["phones"], queryFn: async () => ({ phones: [{ extraction_id: "x1", label: "C3" }] }) }) }))
vi.mock("../components/RecordPanel", () => ({ PhoneRecordPanel: ({ recordUid }: { recordUid: string | null }) => (recordUid ? <p>panel for {recordUid}</p> : null) }))
vi.mock("../ui/AddToMenu", () => ({ AddToMenu: ({ links }: { links: unknown[] }) => <p>add {links.length}</p> }))
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getVirtualItems: () => Array.from({ length: count }, (_, index) => ({ index, start: 36 * (index + 1) })),
    getTotalSize: () => 36 * count,
    scrollToIndex: () => {},
  }),
}))

const row = (id: string, over: Record<string, unknown> = {}) => ({
  record_uid: id, extraction_id: "x1", title: `value ${id}`, time: "Mar 4, 2023", deleted_state: "Intact", interpretation_level: "generic",
  nested: false, copy: false, source_index: null, owner: null, open_in: "panel", cells: { Url: { text: `cell ${id}`, more: 2 } }, ...over,
})
const page = (items: unknown[], total: number, next: string | null = null, over: Record<string, unknown> = {}) => ({
  model_type: "VisitedPage", total, no_time: 0, next, more_fields: 3, zone: "UTC",
  columns: [{ id: "Url", header: "Url", sensitive: false, mapped: false }], items, ...over,
})

function Where() {
  const l = useLocation()
  return <p data-testid="where">{l.pathname + l.search}</p>
}

function show(path = "/cases/c1/phones/x1/records/VisitedPage?placement=top") {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/cases/:id/phones/:extraction/records/conversations" element={<Where />} />
          <Route path="/cases/:id/phones/:extraction/records/:type" element={<><RecordListPage caseId="c1" extraction="x1" modelType="VisitedPage" /><Where /></>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => mocks.list.mockReset())

describe("the list for a record type (03 section 7.5)", () => {
  it("states the exact total from the server and asks for the filter in the address", async () => {
    mocks.list.mockResolvedValue(page([row("a")], 1))
    show()
    expect(await screen.findByText("value a")).toBeInTheDocument()
    expect(mocks.list.mock.calls[0][2]).toMatchObject({ phones: ["x1"], placement: "top" })
    expect(screen.getByText("cell a")).toBeInTheDocument()
    expect(screen.getByText(/more fields are in each record/)).toBeInTheDocument()
  })

  it("fetches the next window near the end and never more than it needs", async () => {
    const first = Array.from({ length: 30 }, (_, i) => row(`r${i}`))
    mocks.list.mockImplementation(async (_c, _t, _f, cursor) => (cursor ? page([row("last")], 31) : page(first, 31, "next-1")))
    show()
    expect(await screen.findByText("value last")).toBeInTheDocument()
    expect(mocks.list).toHaveBeenCalledTimes(2)
    expect(mocks.list.mock.calls[1][3]).toBe("next-1")
  })

  it("opens the record panel for a record and Conversations for a message", async () => {
    mocks.list.mockResolvedValue(page([row("a"), row("m", { open_in: "conversations" })], 2))
    show()
    fireEvent.click(await screen.findByRole("button", { name: "value a" }))
    expect(screen.getByText("panel for a")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "value m" }))
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/records/conversations?record=m"))
  })

  it("marks a copy from another source and links to the record that holds it", async () => {
    mocks.list.mockResolvedValue(page([row("c", { copy: true, nested: true, owner: { record_uid: "own", model_type: "VisitedPage", title: "owner" } })], 1))
    show()
    expect(await screen.findByText(/Copy from another source/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "VisitedPage" }))
    expect(screen.getByText("panel for own")).toBeInTheDocument()
  })

  it("shows a masked value as hidden and a corrected value with its original", async () => {
    mocks.list.mockResolvedValue(page([row("a", { cells: { Url: { text: "••••", more: 0, masked: true } } }), row("b", { cells: { Url: { text: "new", more: 0, original: "old" } } })], 2))
    show()
    expect(await screen.findByLabelText("Hidden sensitive value")).toHaveTextContent("••••")
    expect(screen.getByText(/corrected, was old/)).toBeInTheDocument()
  })

  it("says what a date filter left out", async () => {
    mocks.list.mockResolvedValue(page([row("a")], 1, null, { no_time: 4 }))
    show("/cases/c1/phones/x1/records/VisitedPage?from=2023-03-01")
    expect(await screen.findByText(/4 records have no time and are not in this date range/)).toBeInTheDocument()
  })

  it("says plainly when nothing matches", async () => {
    mocks.list.mockResolvedValue(page([], 0))
    show()
    expect(await screen.findByText("No VisitedPage records match these filters.")).toBeInTheDocument()
  })

  it("asks the server for another order and goes back to the first window", async () => {
    mocks.list.mockResolvedValue(page([row("a")], 1))
    show()
    fireEvent.click(await screen.findByRole("button", { name: /^State/ }))
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("sort=deleted&direction=asc"))
    await waitFor(() => expect(mocks.list.mock.calls.at(-1)?.[2]).toMatchObject({ sort: "deleted", direction: "asc" }))
    expect(mocks.list.mock.calls.at(-1)?.[3]).toBeNull()
  })
})

describe("record list addresses", () => {
  it("round-trip what a Summary count asks for", () => {
    const href = recordListHref("c1", "x1", "Instant Message", { placement: "top", deleted: "only" })
    expect(href).toBe("/cases/c1/phones/x1/records/Instant%20Message?placement=top&deleted=only")
    expect(recordListFilter(href.split("?")[1])).toMatchObject({ placement: "top", deleted: "only" })
  })
  it("drops a value it does not know", () => {
    expect(recordListFilter("?placement=nowhere&sort=size")).toMatchObject({ placement: undefined, sort: undefined })
  })
})
