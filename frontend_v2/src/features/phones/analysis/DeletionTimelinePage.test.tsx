import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 05 section 3.9 (AP-1) and 6.8 for approach 3, deletion and concealment timeline. Invented data only. */
const client = vi.hoisted(() => ({
  runs: vi.fn(), request: vi.fn(), run: vi.fn(), cancel: vi.fn(), coverage: vi.fn(), results: vi.fn(), detail: vi.fn(), decide: vi.fn(),
}))
const pattern = vi.hoisted(() => ({ patternAPI: { keyDates: vi.fn() } }))
vi.mock("./analysis-api", () => ({ analysisAPI: () => client }))
vi.mock("@/features/pattern/api", () => pattern)
vi.mock("@/features/pattern/components/CollectBar", () => ({ CollectBar: () => <div>Add to…</div> }))

import DeletionTimelinePage, { WHAT_IT_DOES } from "./DeletionTimelinePage"
import { TABS, deletionWords } from "./deletion-words"
import { anchorWords } from "./anchor-words"

const RUN = { id: "run-3", approach: "deletion_timeline", status: "completed", progress: {}, error: null,
  counts: { by_kind: { deleted_record: 2, wipe: 1 } },
  coverage: { sentence: "Deleted records exist on 1 of 2 phones (C1). Results below cover those phones only." },
  created_at: "2026-11-03T08:00:00Z", finished_at: "2026-11-03T08:01:00Z" }
const DELETED = {
  id: "res-1", kind: "deleted_record", strength: "interval", label: "Lead for enquiry", decision: null, decisions: [],
  period_start: "2023-03-02T09:00:00Z", period_end: "2023-06-01T08:00:00Z",
  measures: { phone_label: "C1", model_type: "InstantMessage", deleted_state: "Deleted", earliest: "2023-03-02T09:00:00Z",
    latest: "2023-06-01T08:00:00Z", latest_basis: "extraction_start", explanation: "unexplained" },
  directions: { supports: [{ code: "deleted_state_recorded", detail: "The phone report marks this record Deleted.", locators: [] }],
    undercuts: [{ code: "bounded_by_extraction_only", detail: "Deleted at some time between its own time and the extraction; nothing on the phone narrows it.", locators: [] }] },
}

function page(keyDates: unknown[] = []) {
  client.runs.mockResolvedValue({ items: [RUN] })
  client.coverage.mockResolvedValue({ sentence: RUN.coverage.sentence })
  client.results.mockResolvedValue({ total: 2, offset: 0, limit: 100, items: [DELETED] })
  client.detail.mockResolvedValue({ ...DELETED, records: [
    { record_uid: "rec-1", extraction_id: "e1", field_path: null, ledger_transaction_id: null, ledger_ref_id: null, role: "deleted_record" }] })
  pattern.patternAPI.keyDates.mockResolvedValue({ total: keyDates.length, items: keyDates })
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/c1/phone-analyses/deletions"]}>
        <Routes><Route path="/cases/:id/phone-analyses/deletions" element={<DeletionTimelinePage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>)
}

describe("Deleted and hidden (AP-1, 05 6.8)", () => {
  it("shows the seven parts in order, the run's coverage, the full total and the label on every result", async () => {
    page()
    await screen.findByTestId("deletion-result")
    const parts = Array.from(document.querySelectorAll("[data-part]")).map((e) => e.getAttribute("data-part"))
    expect(parts).toEqual(["what", "run", "coverage", "results"])
    expect(screen.getByText(WHAT_IT_DOES)).toBeInTheDocument()
    expect(screen.getByText(RUN.coverage.sentence)).toBeInTheDocument()
    // total is the server's full count under the filter, not the number of rows on screen
    expect(screen.getByTestId("deletion-result-total").textContent).toBe("2 results, showing 1 to 1.")
    for (const r of screen.getAllByTestId("deletion-result")) expect(within(r).getByText("Lead for enquiry")).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Deleted records (2)" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Wipes (1)" })).toBeInTheDocument()
  })

  it("reads 'deleted at some time between [time] and the extraction' (6.8.1, J-11)", async () => {
    page()
    expect(await screen.findByText(/^Deleted at some time between .* and the extraction\. No setting or reason is recorded\.$/)).toBeInTheDocument()
  })

  it("opens the records behind it, Add to…, and refuses a decision without a reason", async () => {
    page()
    fireEvent.click(await screen.findByRole("button", { name: /Message on C1, deleted/ }))
    expect(await screen.findByRole("link", { name: "Open the phone record" })).toHaveAttribute("href", "/cases/c1/records/rec-1")
    expect(screen.getByText("Add to…")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Reject" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Say why, in your own words.")
    expect(client.decide).not.toHaveBeenCalled()
  })

  it("places each result against the case's key dates (6.3 step 6)", async () => {
    page([{ entry_id: "k1", kind: "date", label: "the search", instant_utc: "2023-04-01T00:00:00Z", zone: "UTC", local: null, term: null, title: "" }])
    expect(await screen.findByLabelText("Against key dates")).toHaveTextContent("Could have occurred before or after the search.")
  })

  it("anchor words: before, after, spanning, no period", () => {
    expect(anchorWords("2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z", "2023-02-01T00:00:00Z", "X")).toBe("Before X")
    expect(anchorWords("2023-03-01T00:00:00Z", "2023-03-02T00:00:00Z", "2023-02-01T00:00:00Z", "X")).toBe("After X")
    expect(anchorWords("2023-01-01T00:00:00Z", "2023-03-02T00:00:00Z", "2023-02-01T00:00:00Z", "X")).toBe("Could have occurred before or after X")
    expect(anchorWords(null, null, "2023-02-01T00:00:00Z", "X")).toBeNull()
  })

  it("no tab or row wording states a state of mind or uses an em dash (05 3.5)", () => {
    const kinds = ["deleted_record", "selective_clearing", "hole", "hole_confirmed_by_counterpart", "referenced_message_absent", "concealment_app", "app_removed", "wipe", "power_off", "scrambled_messages"]
    expect(TABS.map((t) => t.kind)).toEqual(kinds)
    const words = kinds.map((k) => deletionWords({ ...DELETED, kind: k, measures: { ...DELETED.measures, categories: ["FakeGPS"], instant: "2023-01-01T00:00:00Z", messages: 3, deleted: 2, share: 0.5, baseline_share: 0.02, p: 0.001, q: 0.01, gap_days: 30, gap_start: "2023-01-01T00:00:00Z", gap_end: "2023-01-31T00:00:00Z", app_messages_elsewhere_in_gap: 4, removed: "2023-02-01T00:00:00Z", counterpart_phones: ["C2"], counterpart_messages_in_gap: 2, counterpart_absent_here: 1, counterpart_deleted_here: 1 } }))
    const text = JSON.stringify(words) + WHAT_IT_DOES + JSON.stringify(TABS)
    expect(text).not.toMatch(/—/)
    expect(text.toLowerCase()).not.toMatch(/intend|wanted to|tried to|knew|deliberat|in order to hide/)
  })
})

it("waits for the run before listing results", async () => {
  client.results.mockClear()
  client.runs.mockResolvedValue({ items: [] })
  client.coverage.mockResolvedValue({ sentence: "Deleted records exist on none of the 1 phones." })
  pattern.patternAPI.keyDates.mockResolvedValue({ total: 0, items: [] })
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/c1/x"]}><Routes><Route path="/cases/:id/x" element={<DeletionTimelinePage />} /></Routes></MemoryRouter>
    </QueryClientProvider>)
  await waitFor(() => expect(screen.getByText("Not run yet in this case. Press Run.")).toBeInTheDocument())
  expect(client.results).not.toHaveBeenCalled()
})
