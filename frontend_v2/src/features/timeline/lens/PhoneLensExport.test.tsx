import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"

const net = vi.hoisted(() => ({ calls: [] as { url: string; body: Record<string, unknown> }[] }))
vi.mock("@/lib/api-client", async (orig) => ({
  ...(await orig<object>()),
  fetchAPI: vi.fn(async (url: string, opts: { body: Record<string, unknown> }) => {
    net.calls.push({ url, body: opts.body })
    if (url.endsWith("/timeline/index"))
      return {
        case_id: "c", snapshot: "s1", complete: true, limits: [], counts: { events: 5, entries: 5 },
        items: [{ day: "2023-03-14", count: 5, offsets: "UTC", header: "Tuesday, March 14, 2023", zone_label: "UTC" }],
        no_time_count: 0, no_time_position: "last", zone: { name: "UTC", label: "UTC", basis: "utc_default", mode: "case", note: null },
        full_load_rows: 5000, sort: "oldest_first", total: 5, lanes: [{ key: "p1", label: "C1", count: 5 }],
        hidden: { count: 2, by_kind: { device: 2 }, words: "2 device events and sensor readings hidden." },
        kinds: [], comm_filter_applies: true, other_filter_applies: true,
      }
    if (url.endsWith("/exports/describe"))
      return { case_id: "c", total: 5, messages: 4, calls: 0, other: 1, unconfirmed: 1, phones: 1, collapsed_copies: 0,
        zone: "UTC", left_out: "Saved passwords and card numbers left out.", limits: [], snapshot: "s1",
        hidden: "2 device events and sensor readings hidden.", machine_text: { total: 0, unconfirmed: 0, items: [], items_cap: 50 } }
    if (url.endsWith("/exports")) return { export_id: "x1" }
    if (url.includes("/exports/x1")) return { export_id: "x1", state: "queued", progress: 0, counts: {}, format: "pdf", source: "timeline_lens",
      file: null, error: null, created_at: null, finished_at: null }
    throw new Error(`unexpected ${url}`)
  }),
}))
vi.mock("@/features/phones/components/StreamList", () => ({ StreamList: () => <div data-testid="phone-list" /> }))
import { PhoneLens } from "./PhoneLens"

/** 03 12.2: the Timeline phone lens exports as the all-channel timeline, the lens's own filter and totals. */
it("exports the lens: the dialog states the lens total and hidden entries, and the export carries the lens filter", async () => {
  render(<MemoryRouter><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <PhoneLens caseId="c" caseName="Synthetic case" />
  </QueryClientProvider></MemoryRouter>)
  const button = await screen.findByRole("button", { name: "Export" })
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)
  expect(await screen.findByText(/All 4 messages and 1 other record, the Case Timeline phone lens \(Messages, Calls, Emails/)).toBeInTheDocument()
  expect(screen.getAllByText("2 device events and sensor readings hidden.").length).toBeGreaterThanOrEqual(1)
  // the scope reads mid-sentence; the cover title it seeds starts with a capital
  expect(screen.getByDisplayValue(/^The Case Timeline phone lens \(Messages/)).toBeInTheDocument()
  const describe = net.calls.find((c) => c.url.endsWith("/exports/describe"))!
  expect(describe.body.source).toBe("timeline_lens")
  expect((describe.body.filter as { lens_kinds: string[] }).lens_kinds).toEqual(["messages", "calls", "emails", "media", "locations"])
  fireEvent.click(screen.getByRole("button", { name: "Export PDF" }))
  await waitFor(() => expect(net.calls.some((c) => c.url.endsWith("/api/phones/exports"))).toBe(true))
  const made = net.calls.find((c) => c.url.endsWith("/api/phones/exports"))!
  expect(made.body.source).toBe("timeline_lens")
  expect((made.body.filter as { lane_by: string }).lane_by).toBe("phone")
})
