import { render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 05 3.9 (AP-1) and 8.8 for approach 5, complementary-use part. Invented data only. */
const client = vi.hoisted(() => ({
  runs: vi.fn(), request: vi.fn(), run: vi.fn(), cancel: vi.fn(), coverage: vi.fn(), results: vi.fn(), detail: vi.fn(), decide: vi.fn(),
}))
vi.mock("./analysis-api", () => ({ analysisAPI: () => client }))
vi.mock("@/features/pattern/api", () => ({ patternAPI: { keyDates: vi.fn().mockResolvedValue({ total: 0, items: [] }) } }))
vi.mock("@/features/pattern/components/CollectBar", () => ({ CollectBar: () => <div>Add to…</div> }))

import DeviceUsersPage, { WHAT_IT_DOES } from "./DeviceUsersPage"
import { deviceWords } from "./device-words"

const RUN = { id: "run-5", approach: "device_users", status: "completed", progress: {}, error: null, counts: { by_kind: { shared_markers: 1 } },
  coverage: { sentence: "Records of the owner using the phone exist on all 2 phones." }, created_at: "2026-11-03T08:00:00Z", finished_at: "2026-11-03T08:01:00Z" }
const NOTE = "Rule of thumb (no measurement behind it): the plan asked for 200 such quarter hours for a pair before comparing places; the most here is 0."
const MARK = { id: "m1", kind: "shared_markers", strength: "strong", label: "Lead for enquiry", decision: null, decisions: [], period_start: null, period_end: null,
  measures: { phones: ["C1", "C2"], by_kind: { iccid: 1 } }, directions: { supports: [], undercuts: [] } }

describe("Who used which phone (AP-1, 05 8.8)", () => {
  it("words a moderate marker in the one scale's word, also for runs stored as medium", () => {
    for (const strength of ["moderate", "medium"]) {
      const w = deviceWords({ ...MARK, strength, measures: { phones: ["C1", "C2"], by_kind: { account: 2 } } })
      expect(w.line).toContain("Strongest kind: moderate.")
    }
  })

  it("lays out the parts and the counts behind together and apart", async () => {
    client.runs.mockResolvedValue({ items: [RUN] })
    client.coverage.mockResolvedValue({ sentence: RUN.coverage.sentence, notes: [NOTE] })
    client.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [MARK] })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/cases/c1/x"]}><Routes><Route path="/cases/:id/x" element={<DeviceUsersPage />} /></Routes></MemoryRouter>
      </QueryClientProvider>)
    const row = await screen.findByTestId("device-user-result")
    expect(Array.from(document.querySelectorAll("[data-part]")).map((e) => e.getAttribute("data-part"))).toEqual(["what", "run", "coverage", "results"])
    expect(screen.getByText(WHAT_IT_DOES)).toBeInTheDocument()
    expect(within(screen.getByTestId("device-user-result-notes")).getByText(NOTE)).toBeInTheDocument()
    expect(screen.getByTestId("device-user-result-strengths").textContent).toBe("By strength: In common: none; Used in turn: none; Together or apart: none; Used while apart: none.")
    expect(screen.getByTestId("device-user-result-total").textContent).toBe("1 result.")
    expect(within(row).getByText("Lead for enquiry")).toBeInTheDocument()
    expect(row).toHaveTextContent("C1 and C2 have 1 SIM card number in common")
  })

  it("words use in turn as numbers, never as who used the phone", () => {
    const w = deviceWords({ ...MARK, kind: "complementary_use", strength: "measured",
      measures: { phones: ["C1", "C2"], days: 14, both: 0, only_x: 168, only_y: 168, neither: 1008, phi: -0.14, switches_per_day: 1, first_day: "2023-01-02", last_day: "2023-01-15" } })
    expect(w.title).toBe("C1 and C2: 14 days with use on both")
    const g = deviceWords({ ...MARK, kind: "complementary_use", strength: "weak",
      measures: { phones: ["C1", "C2"], days: 1, both: 0, only_x: 4, only_y: 4, neither: 88, phi: -0.1, switches_per_day: 1, first_day: "2023-01-02", last_day: "2023-01-02" } })
    expect(g.title).toBe("Weak. C1 and C2: 1 day with use on both")
    expect(JSON.stringify(w) + WHAT_IT_DOES).not.toMatch(/same person|used by one person|—|owner used/)
  })

  it("words together and apart as compatible positions with the strength first, never as one person", () => {
    const w = deviceWords({ ...MARK, kind: "co_location", strength: "weak",
      measures: { phones: ["C1", "C2"], bins_both_placed: 10, together: 10, apart: 0, indeterminate: 0, C: 1, together_tight: 10, together_by_wifi: 0 } })
    expect(w.title).toBe("Weak. C1 and C2: 10 quarter hours with both placed")
    expect(w.line).toContain("100 percent of decided quarter hours together")
    const u = deviceWords({ ...MARK, kind: "use_while_apart", strength: "faint", measures: { phones: ["C1", "C2"], used_phone: "C1", other_phone: "C2", bins: [{}] } })
    expect(u.title).toBe("Faint. C1 used while C2 was elsewhere")
    expect(JSON.stringify([w, u])).not.toMatch(/same person|—/)
  })
})
