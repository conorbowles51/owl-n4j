import { fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 05 3.9 (AP-1) and 5.4 for approach 2. Invented data only. */
const client = vi.hoisted(() => ({
  runs: vi.fn(), request: vi.fn(), run: vi.fn(), cancel: vi.fn(), coverage: vi.fn(), results: vi.fn(), detail: vi.fn(), decide: vi.fn(), keep: vi.fn(), approach: "message_reconciliation",
}))
vi.mock("./analysis-api", () => ({ analysisAPI: () => client }))
const pattern = vi.hoisted(() => ({ keyDates: vi.fn().mockResolvedValue({ total: 0, items: [] }), snapshot: vi.fn() }))
vi.mock("@/features/pattern/api", () => ({ patternAPI: pattern }))
vi.mock("@/features/pattern/components/CollectBar", () => ({ CollectBar: () => <div>Add to…</div> }))

import MessagesAcrossPhonesPage, { WHAT_IT_DOES } from "./MessagesAcrossPhonesPage"
import { messageWords } from "./message-words"

const RUN = { id: "run-2", approach: "message_reconciliation", status: "completed", progress: {}, error: null, counts: { by_kind: { deleted_one_side: 1 } },
  coverage: { sentence: "Messages with a time exist on all 2 phones. A known owner exists on all 2 phones." }, created_at: "2026-11-03T08:00:00Z", finished_at: "2026-11-03T08:01:00Z" }
const base = { label: "Lead for enquiry", decision: null, decisions: [], period_start: "2023-03-01T09:00:00Z", period_end: "2023-03-01T09:00:01Z",
  directions: { supports: [], undercuts: [] } }
const DEL = { ...base, id: "d1", kind: "deleted_one_side", strength: "matched_strong",
  measures: { phones: ["C1", "C2"], tier: "matched_strong", seconds_apart: 1, offset_s: 0, deleted: [true, false], recovered_from: "C2" } }

describe("Messages across phones (AP-1, 05 5.4)", () => {
  it("lays out the parts and says which copy a deleted message is read from", async () => {
    client.runs.mockResolvedValue({ items: [RUN] })
    client.coverage.mockResolvedValue({ sentence: RUN.coverage.sentence })
    client.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [DEL] })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/cases/c1/x"]}><Routes><Route path="/cases/:id/x" element={<MessagesAcrossPhonesPage />} /></Routes></MemoryRouter>
      </QueryClientProvider>)
    const row = await screen.findByTestId("message-result")
    expect(Array.from(document.querySelectorAll("[data-part]")).map((e) => e.getAttribute("data-part"))).toEqual(["what", "run", "coverage", "results"])
    expect(screen.getByText(WHAT_IT_DOES)).toBeInTheDocument()
    expect(within(row).getByText("Lead for enquiry")).toBeInTheDocument()
    expect(row).toHaveTextContent("Deleted on C1, still on C2")
    expect(row).toHaveTextContent("The text is read from C2's copy; C1's record is unchanged. 1 second apart.")
  })

  it("words each kind without saying who wrote, read or deleted", () => {
    const both = messageWords({ ...base, id: "b", kind: "both_sides", strength: "matched_content_time", measures: { phones: ["C1", "C2"], seconds_apart: -300, seconds_after_offset: 5, offset_s: 305 } } as never)
    expect(both.title).toBe("Message on C1 and C2")
    expect(both.line).toBe("300 seconds apart; 5 seconds once the clocks' offset of 305 seconds is allowed for. Text and time agree; one copy does not name its sender.")
    const one = messageWords({ ...base, id: "o", kind: "one_side_only", strength: "unexplained", measures: { on: "C1", not_on: "C2", phones: ["C1", "C2"] } } as never)
    expect(one.line).toBe("No reason found in the records why C2 has no copy.")
    const all = [both, one].map((w) => `${w.title} ${w.line}`).join(" ")
    expect(all).not.toMatch(/\b(knew|intended|tried to|hid|concealed)\b/i)
    expect(all).not.toMatch(/—/)
  })
})

describe("Keeping a result (02 decision 50)", () => {
  function mount(path: string) {
    client.runs.mockResolvedValue({ items: [RUN] })
    client.coverage.mockResolvedValue({ sentence: RUN.coverage.sentence })
    client.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [DEL] })
    client.detail.mockResolvedValue({ ...DEL, records: [] })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={[path]}><Routes><Route path="/cases/:id/x" element={<MessagesAcrossPhonesPage />} /></Routes></MemoryRouter>
      </QueryClientProvider>)
  }

  it("freezes the result and offers Add to… for the kept result", async () => {
    client.keep.mockResolvedValue({ id: "pa_1", kind: "analysis_result", label: "Messages across phones: deleted one side, C1 and C2 (Lead for enquiry)", record_count: 2, stale: false, stale_words: null, snapshot: { summary_counts: { records: 2 }, window: { start: "", end: "", zone: "" } } })
    mount("/cases/c1/x")
    fireEvent.click(await screen.findByRole("button", { name: "Deleted on C1, still on C2" }))
    fireEvent.click(await screen.findByRole("button", { name: "Keep this result" }))
    expect(await screen.findByText(/Kept: Messages across phones: deleted one side, C1 and C2 \(Lead for enquiry\), 2 records behind it\./)).toBeInTheDocument()
    expect(client.keep).toHaveBeenCalledWith("c1", "d1")
  })

  it("opened from a kept link, says what was kept and whether the readings moved", async () => {
    pattern.snapshot.mockResolvedValue({ id: "pa_1", kind: "analysis_result", label: "Messages across phones: both sides", record_count: 2, stale: true,
      stale_words: "The phones' readings changed after this result was frozen; the frozen result is kept as it was.", created_by_name: "Synthetic Reviewer", snapshot: { summary_counts: {}, window: { start: "", end: "", zone: "" } } })
    mount("/cases/c1/x?kept=pa_1")
    const panel = await screen.findByRole("region", { name: "Kept result" })
    expect(panel).toHaveTextContent("Kept result: Messages across phones: both sides")
    expect(panel).toHaveTextContent("2 records behind it, kept by Synthetic Reviewer.")
    expect(panel).toHaveTextContent("The phones' readings changed after this result was frozen")
    expect(pattern.snapshot).toHaveBeenCalledWith("c1", "pa_1")
  })
})
