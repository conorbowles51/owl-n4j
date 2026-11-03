import { render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 05 10.8 (approach 7) and 12.8 (approach 9) on the screens, AP-1 layout. Invented data only. */
const client = vi.hoisted(() => ({
  runs: vi.fn(), request: vi.fn(), run: vi.fn(), cancel: vi.fn(), coverage: vi.fn(), results: vi.fn(), detail: vi.fn(), decide: vi.fn(),
}))
const keyDates = vi.hoisted(() => vi.fn())
vi.mock("./analysis-api", () => ({ analysisAPI: () => client }))
vi.mock("@/features/pattern/api", () => ({ patternAPI: { keyDates } }))
vi.mock("@/features/pattern/components/CollectBar", () => ({ CollectBar: () => <div>Add to…</div> }))

import TypedWordsPage, { NOT_INCLUDED, WHAT_IT_DOES } from "./TypedWordsPage"
import IntentPage from "./IntentPage"
import { intentAnchor } from "./intent-words"
import { recordsWords } from "./count-words"

const run = (approach: string, by_kind: Record<string, number>) => ({ id: "run-" + approach, approach, status: "completed", progress: {}, error: null,
  counts: { by_kind }, coverage: { sentence: "Coverage sentence." }, created_at: "2026-11-03T08:00:00Z", finished_at: "2026-11-03T08:01:00Z" })
const base = { label: "Lead for enquiry", decision: null, decisions: [], directions: { supports: [], undercuts: [] } }
const TYPED = { ...base, id: "t1", kind: "typed_not_in_extraction", strength: "not_elsewhere", period_start: null, period_end: null, sensitive: true,
  measures: { phone_label: "C1", record_type: "DictionaryWord", value_masked: "••••", term_kinds: ["account_ending"], terms_matched: 1,
    frequency: "7", autofill_key: null, first_time: null, last_time: null, elsewhere_records: 0, elsewhere_linked: 0 } }
const PAGE = { ...base, id: "p1", kind: "page_hit", strength: "specific_term", period_start: "2023-03-01T12:00:00Z", period_end: "2023-03-01T12:00:00Z",
  measures: { phone_label: "C1", text: "Synthetic page title", url: null, matched_in: ["title"], term_kinds: ["contact_name"], terms_matched: 1,
    time_meaning: "last_visit_only", instant: "2023-03-01T12:00:00Z", visit_count: "5", origin: null, source: null } }
const SEARCH = { ...base, id: "s1", kind: "search_hit", strength: "common_term", period_start: null, period_end: null,
  measures: { phone_label: "C1", text: "synthetic search", url: null, matched_in: ["search"], term_kinds: ["contact_name"], terms_matched: 1,
    time_meaning: "not_recorded", instant: null, visit_count: null, origin: null, source: null } }

function mount(el: React.ReactNode, path: string) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/c1/" + path]}><Routes><Route path={"/cases/:id/" + path} element={el} /></Routes></MemoryRouter>
    </QueryClientProvider>)
}

describe("Typed words (05 10.8)", () => {
  it("shows the kind of term, never the value, and says how to reveal it", async () => {
    keyDates.mockResolvedValue({ total: 0, items: [] })
    client.runs.mockResolvedValue({ items: [run("typed_words", { typed_not_in_extraction: 1 })] })
    client.coverage.mockResolvedValue({ sentence: "Coverage sentence." })
    client.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [TYPED] })
    mount(<TypedWordsPage />, "phone-analyses/typed-words")
    const row = await screen.findByTestId("typed-result")
    expect(Array.from(document.querySelectorAll("[data-part]")).map((e) => e.getAttribute("data-part"))).toEqual(["what", "run", "coverage", "results"])
    expect(screen.getByText(WHAT_IT_DOES)).toBeInTheDocument()
    expect(screen.getByText(NOT_INCLUDED)).toBeInTheDocument()
    expect(within(row).getByText("Lead for enquiry")).toBeInTheDocument()
    expect(row).toHaveTextContent("Keyboard learned word on C1 matches an account ending in the financial records")
    expect(row).toHaveTextContent("Not found in any message, email, note, search or calendar entry this extraction holds.")
    expect(row).toHaveTextContent("press Reveal")
    expect(row).toHaveTextContent("No time recorded")
    expect(document.body.textContent).not.toMatch(/—/)
  })
})

describe("Searches and pages (05 12.8)", () => {
  it("12.8.1: a page last visited after a key date is never shown as visited before it", () => {
    expect(intentAnchor(PAGE as never, "2023-02-01T00:00:00Z", "the arrest")).toBe("Last visited after the arrest; earlier visits are not dated")
    expect(intentAnchor(PAGE as never, "2023-04-01T00:00:00Z", "the arrest")).toBe("Every recorded visit was before the arrest")
  })

  it("12.8.2: an undated search says time not recorded and is placed against no key date", async () => {
    keyDates.mockResolvedValue({ total: 1, items: [{ label: "the arrest", instant_utc: "2023-02-01T00:00:00Z" }] })
    client.runs.mockResolvedValue({ items: [run("intent", { search_hit: 1, page_hit: 1 })] })
    client.coverage.mockResolvedValue({ sentence: "Coverage sentence." })
    client.results.mockImplementation((_c: string, _r: string, q: { kind: string }) =>
      Promise.resolve({ total: 1, offset: 0, limit: 100, items: [q.kind === "page_hit" ? PAGE : SEARCH] }))
    mount(<IntentPage />, "phone-analyses/searches")
    const row = await screen.findByTestId("intent-result")
    expect(row).toHaveTextContent("Search: synthetic search")
    expect(row).toHaveTextContent("Time not recorded")
    expect(within(row).queryByLabelText("Against key dates")).toBeNull()
    expect(row).toHaveTextContent("may be a business or site name")
  })
})

describe("Kept result words", () => {
  it("says 1 record, not 1 records", () => {
    expect(recordsWords(1)).toBe("1 record")
    expect(recordsWords(2)).toBe("2 records")
  })
})
