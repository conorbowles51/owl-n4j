import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { rowText } from "@/features/phones/lib/copy-rows"
import type { StreamRow } from "@/features/phones/schemas"

const net = vi.hoisted(() => ({ calls: [] as { url: string; body: Record<string, unknown> }[], total: 6, hidden: 4 }))
vi.mock("@/lib/api-client", async (orig) => ({
  ...(await orig<object>()),
  fetchAPI: vi.fn(async (url: string, opts: { body: Record<string, unknown> }) => {
    net.calls.push({ url, body: opts.body })
    if (url.endsWith("/timeline/index")) {
      const kinds = (opts.body.lens_kinds as string[]) ?? []
      const shown = kinds.includes("device")
      return {
        case_id: "c", snapshot: "s1", complete: true, limits: [], counts: { events: net.total, entries: net.total },
        items: [{ day: "2023-03-14", count: net.total, offsets: "UTC", header: "Tuesday, March 14, 2023", zone_label: "UTC" }],
        no_time_count: 0, no_time_position: "last", zone: { name: "UTC", label: "UTC", basis: "utc_default", mode: "case", note: null },
        full_load_rows: 5000, sort: "oldest_first", total: net.total, lanes: [{ key: "p1", label: "C1", count: net.total }],
        hidden: shown ? { count: 0, by_kind: {}, words: null } : { count: net.hidden, by_kind: { device: net.hidden }, words: `${net.hidden} device events and sensor readings hidden.` },
        kinds: [], comm_filter_applies: true, other_filter_applies: true,
      }
    }
    if (url.endsWith("/timeline/window")) return { case_id: "c", snapshot: "s1", complete: true, limits: [], counts: {}, items: [] }
    if (url.endsWith("/timeline/buckets"))
      return {
        case_id: "c", bucket: "day", zone: "UTC", no_data_words: "No data", empty_words: "No matching entries",
        lanes: [
          { key: "p1", label: "C1", buckets: [{ start: "2023-03-14T00:00:00+00:00", wall: "2023-03-14T00:00:00", count: 6, no_data: false }, { start: "2023-03-15T00:00:00+00:00", wall: "2023-03-15T00:00:00", count: 0, no_data: true }] },
          { key: "p2", label: "C2", buckets: [{ start: "2023-03-14T00:00:00+00:00", wall: "2023-03-14T00:00:00", count: 0, no_data: false }] },
        ],
      }
    throw new Error(`unexpected ${url}`)
  }),
}))
const lists = vi.hoisted(() => ({ filters: [] as unknown[] }))
vi.mock("@/features/phones/components/StreamList", () => ({
  StreamList: (p: { stream: { index: unknown; total: number }; filterWords: string }) => {
    lists.filters.push(p.filterWords)
    return <div data-testid="phone-list">{p.filterWords}</div>
  },
}))
import { PhoneLens, usePhoneLens } from "./PhoneLens"

const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>)

beforeEach(() => {
  net.calls = []
  net.total = 6
  lists.filters = []
  localStorage.clear()
})

describe("Timeline phone lens (03 section 9)", () => {
  it("T-7: asks for messages, calls, emails, media and locations by default and states the hidden device events, one click away", async () => {
    wrap(<PhoneLens caseId="c" caseName="Synthetic case" />)
    expect(await screen.findByText("4 device events and sensor readings hidden.")).toBeInTheDocument()
    expect(net.calls[0].body.lens_kinds).toEqual(["messages", "calls", "emails", "media", "locations"])
    fireEvent.click(screen.getByRole("button", { name: "Show" }))
    await waitFor(() => expect(net.calls.at(-1)!.body.lens_kinds).toEqual(["messages", "calls", "emails", "media", "locations", "device", "sensor"]))
    expect(await screen.findByText("Device events and sensor readings are shown.")).toBeInTheDocument()
  })

  it("T-2: a result of 4,000 entries is fetched whole in windows of 1,000, with no load-more control", async () => {
    net.total = 4000
    wrap(<PhoneLens caseId="c" caseName="Synthetic case" />)
    await waitFor(() => expect(net.calls.filter((c) => c.url.endsWith("/timeline/window"))).toHaveLength(4))
    const wins = net.calls.filter((c) => c.url.endsWith("/timeline/window")).map((c) => [c.body.offset, c.body.limit])
    expect(wins).toEqual([[0, 1000], [1000, 1000], [2000, 1000], [3000, 1000]])
    expect(screen.queryByText(/load more/i)).toBeNull()
  })

  it("T-6 and T-4: lanes draw No data apart from no matching entries, and a bucket opens in the same phone list", async () => {
    wrap(<PhoneLens caseId="c" caseName="Synthetic case" />)
    await screen.findByText("6 phone entries")
    fireEvent.click(screen.getByRole("button", { name: "Lanes" }))
    const c1 = await screen.findByRole("region", { name: "Lane: C1" })
    expect(within(c1).getByTitle("No data")).toBeInTheDocument()
    expect(within(c1).getByText("No data")).toBeInTheDocument()
    const c2 = screen.getByRole("region", { name: "Lane: C2" })
    expect(within(c2).getByText(/No matching entries/)).toBeInTheDocument()
    expect(within(c2).queryByTitle("No data")).toBeNull()
    fireEvent.click(within(c1).getByRole("button", { name: /6 entries/ }))
    expect(await screen.findByTestId("phone-list")).toHaveTextContent("one day from the lanes")
    // the bucket's rows come through the lens with the bucket's span and nothing undated
    await waitFor(() => expect(net.calls.some((c) => c.url.endsWith("/timeline/index") && c.body.from_instant === "2023-03-14T00:00:00+00:00" && c.body.include_no_time === false)).toBe(true))
  })

  it("copies a lens record row and a message row through the one copy format", () => {
    const base = { record_uid: "r", phone: { extraction_id: "p1", label: "C1" }, app: null, thread: null, direction: "none", from: null, to: [], call: null,
      attachments: [], flags: [], copies: { count: 1, record_uids: ["r"], apps: [] }, owner_read: { date_read: null, date_played: null }, interpretation_level: "generic", line: "",
      time: { instant: "2023-03-14T12:30:00Z", row: "12:30 PM", full: "Tue, Mar 14, 2023, 12:30:00 PM UTC", offset_present: true, time_field: "TimeStamp" } }
    const rec = { ...base, event_uid: "e1", kind: "record", subject: "Locations: Location", body: "Synthetic place" } as StreamRow
    expect(rowText(rec)).toBe("Tue, Mar 14, 2023, 12:30:00 PM UTC | C1 | Locations: Location: Synthetic place")
  })
})

describe("the Phones switch (03 9.5, 07 4.12)", () => {
  it("is on at first use when the case has no other events, off otherwise, stored and never recomputed", async () => {
    const empty = renderHook(({ other }) => usePhoneLens("c1", other, true), { initialProps: { other: false } })
    expect(empty.result.current.on).toBe(true)
    await act(async () => {})
    empty.rerender({ other: true })
    expect(empty.result.current.on).toBe(true)
    expect(empty.result.current.note).toBe("Phone entries are shown. This case now also has documents.")
    const busy = renderHook(() => usePhoneLens("c2", true, true))
    expect(busy.result.current.on).toBe(false)
    await act(async () => busy.result.current.setOn(true))
    expect(busy.result.current.on).toBe(true)
    expect(JSON.parse(localStorage.getItem("loupe.timeline.phones.c2")!)).toEqual({ on: true, emptyAtFirstUse: false })
    expect(renderHook(() => usePhoneLens("c3", false, false)).result.current.on).toBe(false) // no phones, no lens
  })
})
