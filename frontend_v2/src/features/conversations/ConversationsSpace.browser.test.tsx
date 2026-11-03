import "@/styles/globals.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { Profiler } from "react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { TooltipProvider } from "@/components/ui/tooltip"

/** 03 A15: the communications stream uses the space it is given. Synthetic data only. */
const DAYS = Array.from({ length: 6 }, (_, d) => {
  const iso = new Date(Date.UTC(2023, 0, 1 + d)).toISOString().slice(0, 10)
  return { day: iso, count: 40, offsets: "UTC", header: `Day ${iso}`, zone_label: "UTC" }
})
const row = (n: number, day: string) => ({
  event_uid: `e${n}`, record_uid: `r${n}`, kind: "message", phone: { extraction_id: "e1", label: "C1" }, app: "SyntheticApp", thread: null,
  direction: "incoming", time: { instant: `${day}T12:00:00Z`, row: "12:00 PM", full: `Synthetic ${day} 12:00:00 PM UTC`, offset_present: true, time_field: "TimeStamp" },
  from: null, to: [], body: `synthetic row ${n}`, subject: null, call: null, attachments: [], flags: [], copies: { count: 1, record_uids: [`r${n}`], apps: [] },
  owner_read: { date_read: null, date_played: null }, interpretation_level: "reviewed", line: "",
})
const api = vi.hoisted(() => ({
  getPhones: vi.fn(async () => ({ case_id: "case-1", phones: [{ extraction_id: "e1", label: "C1" }], total: 1, case_zone: { name: "UTC", basis: "utc_default", note: null } })),
  getSettings: vi.fn(async () => ({ case_id: "case-1", time_zone: null, effective: { name: "UTC", basis: "default", note: null }, updated_at: null, updated_by: null })),
  getThreads: vi.fn(async () => ({ case_id: "case-1", snapshot: "s", complete: true, limits: [], counts: { threads: 1, threads_total: 1, reviewed: 0, not_reviewed: 1 }, sort: "recent",
    items: [{ thread_key: "t1", phone: { extraction_id: "e1", label: "C1" }, app: "SyntheticApp", chat_type: null, thread_kind: "chat", title: "Synthetic thread", participants: [], participant_count: 2,
      first_instant: null, last_instant: null, last_full: "", event_count: 240, event_count_total: 240, deleted_count: 0, has_unreadable: false, review: null }] })),
  getParticipants: vi.fn(async () => ({ items: [], counts: { participants: 0 } })),
  getLinkedIdentities: vi.fn(async () => ({ items: [] })),
  streamIndex: vi.fn(async () => ({ case_id: "case-1", snapshot: "s1", complete: true, limits: [], counts: { events: 240, records: 240, collapsed_copies: 0, no_time: 0 },
    items: DAYS, no_time_count: 0, no_time_position: "last", zone: { name: "UTC", label: "UTC", basis: "default", mode: "case", note: null }, full_load_rows: 5000, sort: "oldest_first" })),
  streamWindow: vi.fn(async (_f: unknown, _s: string, day: string | null, offset: number, limit: number) => ({
    case_id: "case-1", snapshot: "s1", complete: true, limits: [], counts: {},
    items: Array.from({ length: Math.min(limit, 40 - offset) }, (_, i) => row(DAYS.findIndex((d) => d.day === day) * 40 + offset + i, day ?? "")) })),
}))
vi.mock("@/features/phones/api", async (orig) => ({ ...(await orig<object>()), ...api }))
const stable = vi.hoisted(() => ({ kase: { data: { title: "Synthetic case" } }, targets: { data: [] }, used: { usedIn: {}, refresh: () => {} } }))
vi.mock("@/features/cases/hooks/use-cases", () => ({ useCase: () => stable.kase }))
vi.mock("@/features/phones/hooks/use-collect", () => ({ useCollectTargets: () => stable.targets, useUsedIn: () => stable.used }))
vi.mock("@/lib/ux-events", () => ({ trackUx: vi.fn() }))
import ConversationsPage from "./ConversationsPage"

afterEach(() => cleanup())

it("the list does not make the page render forever once rows load (review of A15: the selection is reported once)", async () => {
  await page.viewport(1280, 800)
  const commits = { n: 0 }
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TooltipProvider>
        <MemoryRouter initialEntries={["/cases/case-1/conversations?thread=t1"]}>
          <div style={{ height: "100vh", overflow: "hidden" }} className="flex flex-col">
            <Profiler id="page" onRender={() => void commits.n++}>
              <Routes><Route path="/cases/:id/conversations" element={<ConversationsPage />} /></Routes>
            </Profiler>
          </div>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  )
  await screen.findByText("synthetic row 0")
  await new Promise((r) => setTimeout(r, 300))
  const settled = commits.n
  await new Promise((r) => setTimeout(r, 700))
  // with nothing happening on screen, the page does not keep rendering
  expect(commits.n - settled).toBeLessThan(5)
})

function show() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TooltipProvider>
        <MemoryRouter initialEntries={["/cases/case-1/conversations?thread=t1"]}>
          <div style={{ height: "100vh", overflow: "hidden" }} className="flex flex-col">
            <Routes><Route path="/cases/:id/conversations" element={<ConversationsPage />} /></Routes>
          </div>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

const rowsShown = () => document.querySelectorAll('[data-index]').length

for (const [w, h] of [[1280, 800], [1920, 1080]] as const) {
  it(`A15: at ${w}x${h} the stream and time strip fill their space with no unused band, and hiding the strip gives the stream its room`, async () => {
    await page.viewport(w, h)
    show()
    const section = await screen.findByRole("region", { name: "Conversation" }).catch(() => null) ?? document.querySelector('section[aria-label="Conversation"]')!
    await screen.findByText("synthetic row 0")
    const strip = await screen.findByRole("group", { name: "Message density" })
    const s = (section as HTMLElement).getBoundingClientRect()
    // the section reaches the bottom of the window: no unused band below the stream and strip
    expect(Math.abs(s.bottom - h)).toBeLessThanOrEqual(2)
    expect(Math.abs(strip.getBoundingClientRect().bottom - s.bottom)).toBeLessThanOrEqual(2)
    const before = rowsShown()
    expect(before).toBeGreaterThan(3)
    fireEvent.click(screen.getByRole("button", { name: "Hide time strip" }))
    await waitFor(() => expect(rowsShown()).toBeGreaterThanOrEqual(before))
    expect(Math.abs((section as HTMLElement).getBoundingClientRect().bottom - h)).toBeLessThanOrEqual(2)
  })
}

it("A15: the number of visible rows grows with the window's height", async () => {
  await page.viewport(1280, 800)
  const a = show()
  await screen.findByText("synthetic row 0")
  const small = rowsShown()
  a.unmount()
  await page.viewport(1280, 1200)
  show()
  await screen.findByText("synthetic row 0")
  await waitFor(() => expect(rowsShown()).toBeGreaterThan(small))
})
