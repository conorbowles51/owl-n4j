import { render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 05 3.9 (AP-1) and 14.8 for approach 11, relationships over time. Invented data only. */
const client = vi.hoisted(() => ({
  runs: vi.fn(), request: vi.fn(), run: vi.fn(), cancel: vi.fn(), coverage: vi.fn(), results: vi.fn(), detail: vi.fn(), decide: vi.fn(),
}))
vi.mock("./analysis-api", () => ({ analysisAPI: () => client }))
vi.mock("@/features/pattern/api", () => ({ patternAPI: { keyDates: vi.fn().mockResolvedValue({ total: 0, items: [] }) } }))
vi.mock("@/features/pattern/components/CollectBar", () => ({ CollectBar: () => <div>Add to…</div> }))

import RelationshipsPage, { WHAT_IT_DOES } from "./RelationshipsPage"
import { relationshipWords } from "./relationship-words"

const RUN = { id: "run-11", approach: "relationships", status: "completed", progress: {}, error: null, counts: { by_kind: { relationship: 1, volume_change: 1 } },
  coverage: { sentence: "Contacts exist on all 2 phones. Contact saved times exist on 1 of 2 phones (C1). Calls and messages exist on all 2 phones. Results below cover those phones only." },
  created_at: "2026-11-03T08:00:00Z", finished_at: "2026-11-03T08:01:00Z" }
const REL = {
  id: "r1", kind: "relationship", strength: "identity", label: "Lead for enquiry", decision: null, decisions: [],
  period_start: "2023-01-02T12:00:00Z", period_end: "2023-01-16T21:00:00Z",
  measures: { phone_label: "C1", extraction_id: "ext-1", group: "phone:+12025550143", identity_keys: ["phone:+12025550143"], names_here: ["Ana S"],
    names_elsewhere: { C2: ["Mum"] }, saved: null, modified: null, contact_cards: 1, communications: 30, untimed: 0,
    first: { message: "2023-01-02T12:00:00Z", call: null, email: null }, last: { message: "2023-01-16T21:00:00Z", call: null, email: null }, monthly: {} },
  directions: { supports: [], undercuts: [] },
}

function page() {
  client.runs.mockResolvedValue({ items: [RUN] })
  client.coverage.mockResolvedValue({ sentence: RUN.coverage.sentence })
  client.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [REL] })
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/c1/phone-analyses/relationships"]}>
        <Routes><Route path="/cases/:id/phone-analyses/relationships" element={<RelationshipsPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>)
}

describe("Relationships over time (AP-1, 05 14.8)", () => {
  it("shows the layout parts in order, the coverage sentence, the total and the label", async () => {
    page()
    const row = await screen.findByTestId("relationship-result")
    expect(Array.from(document.querySelectorAll("[data-part]")).map((e) => e.getAttribute("data-part"))).toEqual(["what", "run", "coverage", "results"])
    expect(screen.getByText(WHAT_IT_DOES)).toBeInTheDocument()
    expect(screen.getByText(RUN.coverage.sentence)).toBeInTheDocument()
    expect(screen.getByTestId("relationship-result-total").textContent).toBe("1 result.")
    expect(within(row).getByText("Lead for enquiry")).toBeInTheDocument()
  })

  it("shows how each phone names the person (14.8.2) and opens their calls and messages", async () => {
    page()
    const row = await screen.findByTestId("relationship-result")
    expect(row).toHaveTextContent("Ana S on C1: 30 calls, messages and emails")
    expect(row).toHaveTextContent("C2 calls them Mum")
    expect(row).toHaveTextContent("Saved as a contact; the phone recorded no saved time.")
    expect(within(row).getByRole("link", { name: "Open their calls and messages" }).getAttribute("href"))
      .toBe("/cases/c1/conversations?tab=people&people=phone%3A%2B12025550143&phones=ext-1")
  })

  it("words a fall in contact with its rates and never a reason", () => {
    const w = relationshipWords({ ...REL, kind: "volume_change", strength: "fall",
      measures: { ...REL.measures, week_start: "2023-01-23", rate_before: 10, rate_after: 0, weeks_before: 3, weeks_after: 3 } })
    expect(w.title).toBe("Contact with Ana S on C1 fell from the week of 2023-01-23")
    expect(w.line).toBe("About 10 a week for 3 weeks, then about 0 a week for 3 weeks.")
    expect(JSON.stringify(w) + WHAT_IT_DOES).not.toMatch(/—|because|argued|fell out|ended the/)
  })
})
