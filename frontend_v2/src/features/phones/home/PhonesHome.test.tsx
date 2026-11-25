import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, useLocation } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { StreamRow } from "../schemas"

// Screen 1 of the phones redesign: every phone on by default, the cards switching phones for the whole page, exact
// counts beside What / Who / State, one list of every kind of record, the record panel following the focused row
// and the weekly strip narrowing everything by drag. Server parts are stubbed; their counts are tested in
// backend/tests/test_phone_home_facets.py.
const m = vi.hoisted(() => ({ facets: vi.fn(), index: vi.fn(), buckets: vi.fn(), stream: vi.fn(), focus: null as ((r: unknown) => void) | null }))
const PHONES = [
  { extraction_id: "p1", label: "Phone 1", standing: "active", owner: { name: "Priya Halloran" }, device: { manufacturer: "Apple", model: "iPhone" }, counts: { messages: 131, calls: 11, locations: 298 } },
  { extraction_id: "p2", label: "Phone 2", standing: "active", owner: { name: "Marisol Teague" }, device: { manufacturer: null, model: null }, counts: { messages: 54, calls: 10, locations: 120 } },
  { extraction_id: "p3", label: "Phone 3", standing: "active", owner: { name: "Dorian Pell" }, device: { manufacturer: null, model: null }, counts: { messages: 59, calls: 10, locations: 301 } },
]
vi.mock("@/features/phones/phones-query", () => ({ phonesQuery: (c: string) => ({ queryKey: ["phones", c], queryFn: async () => ({ phones: PHONES }) }) }))
vi.mock("@/features/phones/phone-queries", () => ({ phoneSettingsQuery: (c: string) => ({ queryKey: ["s", c], queryFn: async () => ({ effective: { name: "UTC" } }) }) }))
vi.mock("@/features/phones/ui/use-phone-scope", async () => {
  const { useLocation, useSearchParams } = await import("react-router-dom")
  const scope = await import("@/features/phones/ui/scope")
  return {
    useUrlScope: () => {
      const l = useLocation()
      const [, set] = useSearchParams()
      const ids = scope.paramsToScopeIds(l.search)
      const s = { ...scope.EMPTY_SCOPE, ...ids, people: ids.people.map((k: string) => ({ key: k, label: k })), phones: ids.phones.map((id: string, index: number) => ({ id, label: id, index })), labels: [] }
      return {
        scope: s, presets: [], notApplied: [], recent: [], restored: false,
        apply: (n: typeof s) => set((p) => { const q = new URLSearchParams(p); for (const k of scope.SCOPE_PARAMS) q.delete(k); for (const [k, v] of Object.entries(scope.scopeToParams(n))) q.set(k, v); return q }),
      }
    },
  }
})
vi.mock("@/features/phones/ui/use-case-phones", () => ({ useCasePhones: () => PHONES.map((p, index) => ({ id: p.extraction_id, label: p.label, index, owner: p.owner.name })) }))
vi.mock("@/features/timeline/lens/lens-api", () => ({ LENS_SOURCE: {}, lensIndex: m.index, lensBuckets: m.buckets }))
vi.mock("./home-api", async (orig) => ({ ...(await orig<typeof import("./home-api")>()), homeFacets: m.facets }))
vi.mock("@/features/phones/hooks/use-stream", () => ({ useStream: (f: unknown) => m.stream(f) }))
vi.mock("@/features/phones/components/StreamList", () => ({
  StreamList: ({ onFocusRow }: { onFocusRow: (r: unknown) => void }) => { m.focus = onFocusRow; return <div data-testid="list" /> },
}))
vi.mock("./HomeRecordPanel", () => ({ HomeRecordPanel: ({ row }: { row: { body: string } | null }) => <aside aria-label="Selected record">{row ? row.body : "nothing chosen"}</aside> }))
vi.mock("@/features/conversations/ExportDialog", () => ({ ExportDialog: () => null }))

import { PhonesHome } from "./PhonesHome"
import { copyKey, phonesByCopy, spanWords } from "./home-words"

function Where() {
  const l = useLocation()
  return <p data-testid="where">{l.search}</p>
}
function show(path = "/cases/c1/phones") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}><PhonesHome caseId="c1" caseName="Corwen Street Dental" /><Where /></MemoryRouter>
    </QueryClientProvider>,
  )
}
const lastFilter = () => m.stream.mock.calls.filter((c) => c[0]).at(-1)![0]

beforeEach(() => {
  vi.clearAllMocks()
  m.facets.mockImplementation(async (_f: unknown, part: string) => ({
    kinds: { kinds: [{ key: "messages", count: 244 }, { key: "calls", count: 31 }, { key: "emails", count: 0 }, { key: "locations", count: 719 }, { key: "device", count: 402 }, { key: "sensor", count: 0 }] },
    people: { people: [{ key: "phone:+17175550261", label: "Nell", count: 80, phones: ["Phone 1"], on: false }], people_total: 3, people_applies: true },
    states: { states: [{ key: "deleted", label: "Deleted or in trash", count: 4 }, { key: "one", label: "On one phone only", count: 241, applies: true }, { key: "many", label: "On more than one phone", count: 34, applies: true }], states_note: "Copies on other phones are judged for messages and calls only." },
    phones: { phones: [{ extraction_id: "p1", first_day: "2024-01-01", last_day: "2024-05-20" }] },
  } as Record<string, object>)[part])
  m.stream.mockReturnValue({ status: "ready", index: { snapshot: "s", items: [{ day: "2024-01-03" }, { day: "2024-01-11" }], counts: { entries: 275 }, zone: { label: "UTC", name: "UTC" } }, total: 275, count: 0, rowsVersion: 0, item: () => ({ type: "header" }) })
  m.buckets.mockResolvedValue({ case_id: "c1", bucket: "week", zone: "UTC", no_data_words: "No data", empty_words: "", lanes: PHONES.map((p) => ({ key: p.extraction_id, label: p.label, buckets: [{ start: "2024-01-01T00:00:00Z", wall: "2024-01-01T00:00:00", count: 6, no_data: false }, { start: "2024-01-08T00:00:00Z", wall: "2024-01-08T00:00:00", count: 9, no_data: false }] })) })
})

describe("the Phones page", () => {
  it("shows a card per phone with owner, span and counts, every phone on, and the list over all of them", async () => {
    show()
    const cards = await screen.findByRole("group", { name: "Phones in this case" })
    await within(cards).findAllByRole("checkbox")
    expect(within(cards).getAllByRole("checkbox").map((c) => (c as HTMLInputElement).checked)).toEqual([true, true, true])
    expect(cards).toHaveTextContent("Priya Halloran")
    expect(await within(cards).findByText(/1 Jan to 20 May 2024/)).toBeInTheDocument()
    expect(cards).toHaveTextContent("131 messages · 11 calls · 298 places")
    expect(within(cards).getByRole("link", { name: "About this phone: Phone 1" })).toHaveAttribute("href", "/cases/c1/phones/p1")
    expect(screen.getByText("275 on 3 phones, oldest first")).toBeInTheDocument()
    expect(lastFilter().phones ?? []).toEqual([]) // every phone
    expect(lastFilter().lens_kinds).toEqual(["messages", "calls", "emails"])
  })

  it("a card's switch turns a phone off for the whole page, and says so", async () => {
    show()
    fireEvent.click(await screen.findByRole("checkbox", { name: "Phone 2 on" }))
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("phones=p1%2Cp3"))
    expect(lastFilter().phones).toEqual(["p1", "p3"])
    expect(screen.getByText(/2 of 3 phones are on/)).toBeInTheDocument()
  })

  it("What, Who and State show exact counts and narrow the list", async () => {
    show()
    const what = await screen.findByRole("group", { name: "What" })
    await waitFor(() => expect(within(what).getByRole("button", { name: /Messages and calls/ })).toHaveTextContent("275"))
    expect(within(what).getByRole("button", { name: /Places/ })).toHaveTextContent("719")
    expect(within(what).getByRole("button", { name: /Device events/ })).toHaveTextContent("402")
    fireEvent.click(within(what).getByRole("button", { name: /Places/ }))
    await waitFor(() => expect(lastFilter().lens_kinds).toEqual(["locations"]))
    const who = screen.getByRole("group", { name: "Who" })
    fireEvent.click(within(who).getByRole("button", { name: /Nell/ }))
    await waitFor(() => expect(lastFilter().participants).toEqual(["phone:+17175550261"]))
    expect(within(who).getByRole("link", { name: "All people (3)" })).toBeInTheDocument()
    const st = screen.getByRole("group", { name: "State" })
    fireEvent.click(within(st).getByRole("button", { name: /On more than one phone/ }))
    await waitFor(() => expect(lastFilter().copies_on).toBe("many"))
    fireEvent.click(within(st).getByRole("button", { name: /Deleted or in trash/ }))
    await waitFor(() => expect(lastFilter().deleted_states).toEqual(["Deleted", "Trash"]))
  })

  it("the record panel follows the focused row", async () => {
    show()
    await screen.findByTestId("list")
    expect(screen.getByRole("complementary", { name: "Selected record" })).toHaveTextContent("nothing chosen")
    m.focus!({ kind: "message", body: "half now, half on Friday", time: { instant: "2024-01-05T03:22:00Z" }, phone: { extraction_id: "p1", label: "Phone 1" } })
    await waitFor(() => expect(screen.getByRole("complementary", { name: "Selected record" })).toHaveTextContent("half now, half on Friday"))
  })

  it("Search words narrows the list in place; Ask a question opens Ask with the words and the scope", async () => {
    show("/cases/c1/phones?phones=p1,p2")
    fireEvent.change(await screen.findByRole("searchbox"), { target: { value: "invoice" } })
    fireEvent.click(screen.getByRole("button", { name: "Search" }))
    await waitFor(() => expect(lastFilter().text).toEqual({ query: "invoice" }))
    expect(screen.getByTestId("where")).toHaveTextContent("q=invoice")
  })

  it("the weekly strip draws a lane per phone and a picked run of weeks narrows the page", async () => {
    show()
    const strip = await screen.findByRole("region", { name: "Activity on each phone" })
    await waitFor(() => expect(strip.querySelectorAll("[data-lane]")).toHaveLength(3))
    const slider = within(strip).getByRole("slider", { name: "Weeks to show" })
    fireEvent.keyDown(slider, { key: "ArrowRight", shiftKey: true })
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("from=2024-01-01&to=2024-01-14"))
    expect(lastFilter().from_instant).toBe("2024-01-01T00:00:00.000Z")
  })

  it("keeps the screens that left the side menu one click away", async () => {
    show()
    const more = await screen.findByRole("navigation", { name: "More about these phones" })
    expect(within(more).getAllByRole("link").map((l) => l.textContent)).toEqual(["Threads and people", "Patterns of life", "Money on the phones", "Analyses", "Needs a decision"])
  })
})

describe("copies on other phones among the loaded rows", () => {
  const row = (phone: string, body: string | null, at: string, kind: StreamRow["kind"] = "message") =>
    ({ kind, body, time: { instant: at }, call: kind === "call" ? { duration_s: 120 } : null, phone: { extraction_id: phone, label: phone } }) as unknown as StreamRow
  it("match on kind, minute and text (a call, its length), the server's rule", () => {
    const map = phonesByCopy([row("p2", "Sent you the invoice", "2024-01-05T11:40:10Z"), row("p3", "Sent you the invoice", "2024-01-05T11:40:50Z"), row("p3", "other", "2024-01-05T11:40:00Z")])
    expect([...map.get(copyKey(row("x", "Sent you the invoice", "2024-01-05T11:40:00Z"))!)!.keys()]).toEqual(["p2", "p3"])
    expect(copyKey(row("p1", null, "2024-01-05T11:40:00Z"))).toBeNull() // no text: never a copy
    expect(copyKey(row("p1", "x", "2024-01-05T11:40:00Z", "record"))).toBeNull()
    expect(copyKey(row("p1", null, "2024-01-05T11:40:00Z", "call"))).toBe("call|2024-01-05T11:40|120")
  })
  it("a span reads as days", () => {
    expect(spanWords("2024-01-01", "2024-05-20")).toBe("1 Jan to 20 May 2024")
    expect(spanWords("2023-12-30", "2024-01-02")).toBe("30 Dec 2023 to 2 Jan 2024")
  })
})
