import "@/styles/globals.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { page, userEvent } from "vitest/browser"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { useStream } from "../hooks/use-stream"
import type { StreamFilter } from "../api"
import { StreamList } from "./StreamList"

/** 03 section 17.1 A4, A5, A7, A13 (and C-1, C-9, T-2) in Chromium, against a mocked server. */

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))

const mocked = vi.mocked(fetchAPI)
let client: QueryClient
afterEach(() => {
  cleanup()
  client?.clear()
  vi.resetAllMocks()
})
beforeEach(async () => {
  await page.viewport(1280, 800)
})

function days(total: number, perDay: number) {
  const out = []
  let left = total
  let d = 0
  while (left > 0) {
    const n = Math.min(perDay, left)
    const date = new Date(Date.UTC(2023, 0, 1 + d))
    const iso = date.toISOString().slice(0, 10)
    out.push({ day: iso, count: n, offsets: "UTC-5", header: `Day ${iso}`, zone_label: "Eastern Time (UTC-5)" })
    left -= n
    d++
  }
  return out
}

function index(total: number, perDay: number, extra: Record<string, unknown> = {}) {
  return {
    case_id: "c", snapshot: "s1", complete: true, limits: [], counts: { events: total, records: total, collapsed_copies: 0, no_time: 0 },
    items: days(total, perDay), no_time_count: 0, no_time_position: "last",
    zone: { name: "America/New_York", label: "Eastern Time", basis: "device_metadata", mode: "phone", note: null },
    full_load_rows: 5000, sort: "oldest_first", ...extra,
  }
}

function makeRow(n: number, day: string) {
  return {
    event_uid: `e${n}`, record_uid: `r${n}`, kind: "message", phone: { extraction_id: "x", label: "C3" }, app: "WhatsApp", thread: null,
    direction: "incoming",
    time: { instant: `${day}T19:07:12Z`, row: "2:07 PM", full: `Synthetic ${day} 2:07:12 PM EST`, offset_present: true, time_field: "TimeStamp" },
    from: { identity_key: "phone:+12025550143", name: "Maria Lopez", name_basis: "contact_on_this_phone", identifier: { kind: "phone", display: "+1 202-555-0143" }, is_owner: false, owner_basis: null, case_names: [] },
    to: [{ identity_key: "phone:+12025550100", name: null, name_basis: "none", identifier: { kind: "phone", display: "+1 202-555-0100" }, is_owner: true, owner_basis: "extracted", phone_label: "C3", case_names: [] }],
    body: `row ${n}`, subject: null, call: null, attachments: [], flags: [], copies: { count: 1, record_uids: [`r${n}`], apps: ["WhatsApp"] },
    owner_read: { date_read: null, date_played: null }, interpretation_level: "reviewed",
    line: "Maria Lopez (+1 202-555-0143) -> Owner of C3 (+1 202-555-0100)",
  }
}

type Body = { filter: unknown; snapshot: string; day: string | null; offset: number; limit: number }

function serve(idx: ReturnType<typeof index>, opts: { failWindow?: number; staleOnce?: boolean; recordTime?: string } = {}) {
  const starts = new Map<string, number>()
  let pos = 0
  for (const d of idx.items) {
    starts.set(d.day, pos)
    pos += d.count
  }
  let fails = opts.failWindow ?? 0
  let stale = !!opts.staleOnce
  const calls = { index: 0, window: 0 }
  mocked.mockImplementation(async (url: string, init?: { body?: unknown }) => {
    if (url.startsWith("/api/phones/streams/index")) {
      calls.index++
      return { ...idx, snapshot: `s${calls.index}` }
    }
    if (url.startsWith("/api/phones/streams/window")) {
      calls.window++
      const b = init?.body as Body
      if (stale) {
        stale = false
        throw new ApiError("stale", 409, { detail: "stale_snapshot" })
      }
      if (fails > 0) {
        fails--
        throw new ApiError("boom", 500, { detail: { text: "These messages could not be loaded. Reference: x." } })
      }
      const base = starts.get(b.day as string) ?? 0
      const items = Array.from({ length: b.limit }, (_, k) => makeRow(base + b.offset + k, b.day as string))
      return { case_id: "c", snapshot: b.snapshot, complete: true, limits: [], counts: {}, items }
    }
    if (url.startsWith("/api/phones/streams/locate")) return { day: idx.items[0].day, offset: 0 }
    if (url.startsWith("/api/phones/records/")) {
      return {
        record_uid: "r0", extraction: { id: "x", label: "C3", report_filename: "synthetic.xml", report_sha256: null }, model_type: "InstantMessage",
        cellebrite_id: "1", title: null, state: { deleted_state: "Intact", is_carved: false, decoding_confidence: null, source_index: null, interpretation_level: "reviewed" },
        fields: [], files: [], files_absence: "This record does not refer to a file.", source_row: { available: false, reason: "x" }, corrections: [],
        times: [{ record_uid: "r0", field_path: "TimeStamp", value_index: 0, instant: "2023-01-01T19:07:12Z", full: "x", original_text: opts.recordTime ?? "2023-01-01T19:07:12.000+00:00", offset_present: true }],
        interpretation_level: "reviewed", zone: "America/New_York", as_text: "x",
      }
    }
    throw new Error(`unexpected ${url}`)
  })
  return calls
}

function Harness({ filter }: { filter: StreamFilter }) {
  const stream = useStream(filter)
  return (
    <div style={{ height: 600, display: "flex", flexDirection: "column" }}>
      <StreamList stream={stream} caseId="c" caseName="Synthetic case" filterWords="none" zoneName="Eastern Time" zone="America/New_York" />
    </div>
  )
}

function mount() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Harness filter={{ case_id: "c" }} />
    </QueryClientProvider>,
  )
}

it("A4 / C-1: a 200,000-row index sizes the list to every row, End reaches the last row, and there is no load-more control", async () => {
  serve(index(200_000, 2_000))
  mount()
  await screen.findByText("200,000 messages")
  const sizer = screen.getByTestId("stream-sizer")
  expect(parseFloat(sizer.style.height)).toBeGreaterThan(200_000 * 50)
  const scroller = screen.getByTestId("stream-scroll")
  scroller.focus()
  fireEvent.keyDown(scroller, { key: "End" })
  await waitFor(() => expect(screen.getByText("row 199999")).toBeTruthy(), { timeout: 15_000 })
  expect(document.body.textContent?.toLowerCase()).not.toContain("load more")
})

it("A4 / T-2: a 4,000-row result loads every row without scrolling", async () => {
  const calls = serve(index(4_000, 4_000))
  mount()
  await screen.findByText("4,000 messages")
  await waitFor(() => expect(calls.window).toBe(4), { timeout: 10_000 })
  expect(document.body.textContent?.toLowerCase()).not.toContain("load more")
})

it("A5: a window that fails twice shows Retry in place, and Retry loads it", async () => {
  serve(index(300, 300, { full_load_rows: 100 }), { failWindow: 2 })
  mount()
  await screen.findByText("300 messages")
  const retry = await screen.findAllByRole("button", { name: "Retry" }, { timeout: 8_000 })
  expect(screen.getAllByText(/These messages could not be loaded/).length).toBeGreaterThan(0)
  fireEvent.click(retry[0])
  await screen.findByText("row 0", undefined, { timeout: 8_000 })
})

it("A5: a list closed while a failed window waits to retry asks for nothing more", async () => {
  const calls = serve(index(300, 300, { full_load_rows: 100 }), { failWindow: 1 })
  const view = mount()
  await screen.findByText("300 messages")
  await screen.findAllByText(/These messages could not be loaded/, undefined, { timeout: 8_000 })
  const asked = calls.window
  view.unmount()
  await new Promise((r) => setTimeout(r, 2_500)) // past the 2-second automatic retry
  expect(calls.window).toBe(asked)
})

it("A5 / C-9: a stale snapshot re-reads the index and says the list was refreshed", async () => {
  const calls = serve(index(50, 50), { staleOnce: true })
  mount()
  await screen.findByText(/New data arrived while you were reading/, undefined, { timeout: 8_000 })
  expect(calls.index).toBe(2)
  await screen.findByText("row 0")
})

it("A7: the day header names the zone and offset, and the original value shows the report's text byte for byte", async () => {
  const original = "2023-01-01T19:07:12.000+00:00"
  serve(index(5, 5), { recordTime: original })
  mount()
  await screen.findByRole("heading", { name: /^Day 2023-01-01, Eastern Time \(UTC-5\)$/ })
  const time = (await screen.findAllByText("2:07 PM"))[0]
  fireEvent.click(time)
  await waitFor(() => expect(document.querySelector('[data-line="In the report"]')?.textContent).toBe(original))
  expect(document.querySelector('[data-line="Offset stored"]')?.textContent).toBe("+00:00 (the report converted this time to UTC)")
})

it("A13: three selected rows and Ctrl+C write text and HTML; Ctrl+A then copy covers the whole result", async () => {
  serve(index(6, 6))
  mount()
  await screen.findByText("row 5")
  const captured: { text: string; html: string }[] = []
  const grab = (e: ClipboardEvent) => captured.push({ text: e.clipboardData?.getData("text/plain") ?? "", html: e.clipboardData?.getData("text/html") ?? "" })
  window.addEventListener("copy", grab)
  try {
    const boxes = screen.getAllByRole("checkbox", { name: "Select this message" })
    await userEvent.click(boxes[0])
    await userEvent.click(boxes[1])
    await userEvent.click(boxes[2])
    await userEvent.keyboard("{Control>}c{/Control}")
    await waitFor(() => expect(captured.length).toBe(1))
    const lines = captured[0].text.split("\n")
    expect(lines.slice(0, 3)).toEqual([0, 1, 2].map((n) => `Synthetic 2023-01-01 2:07:12 PM EST | C3 | WhatsApp | Maria Lopez (+1 202-555-0143) -> Owner of C3 (+1 202-555-0100) | row ${n}`))
    expect(lines[lines.length - 1]).toBe("Copied from Loupe, case Synthetic case, filter: none, times in Eastern Time.")
    expect(captured[0].html).toContain("<table>")
    expect(captured[0].html.match(/<tr>/g)?.length).toBe(4)
    await userEvent.keyboard("{Control>}a{/Control}")
    await screen.findByText("6 messages selected")
    await userEvent.keyboard("{Control>}c{/Control}")
    await waitFor(() => expect(captured.length).toBe(2))
    expect(captured[1].text.split("\n").filter((l) => l.includes(" | C3 | ")).length).toBe(6)
  } finally {
    window.removeEventListener("copy", grab)
  }
})

it("a new filter asks for no window with the previous snapshot while its index loads (review of 03-2)", async () => {
  const idx = index(200_000, 2_000)
  const calls = serve(idx)
  const base = mocked.getMockImplementation()!
  let release: () => void = () => {}
  const held = new Promise<void>((r) => (release = r))
  const windowSnapshots: string[] = []
  let changed = false
  mocked.mockImplementation(async (url: string, init?: { body?: unknown }) => {
    if (changed && url.startsWith("/api/phones/streams/index")) await held
    if (changed && url.startsWith("/api/phones/streams/window")) windowSnapshots.push((init?.body as Body).snapshot)
    return base(url, init as never)
  })
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={client}>
      <Harness filter={{ case_id: "c" }} />
    </QueryClientProvider>,
  )
  await screen.findByText("row 0")
  changed = true
  view.rerender(
    <QueryClientProvider client={client}>
      <Harness filter={{ case_id: "c", apps: ["SMS"] }} />
    </QueryClientProvider>,
  )
  const scroller = screen.getByTestId("stream-scroll")
  scroller.focus()
  fireEvent.keyDown(scroller, { key: "End" })
  await new Promise((r) => setTimeout(r, 500))
  expect(windowSnapshots).toEqual([])
  release()
  await waitFor(() => expect(windowSnapshots.length).toBeGreaterThan(0))
  expect(new Set(windowSnapshots)).toEqual(new Set(["s2"]))
  expect(calls.index).toBe(2)
  expect(document.body.textContent).not.toContain("New data arrived")
})
