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

import DeviceUsersPage, { NOT_BUILT, WHAT_IT_DOES } from "./DeviceUsersPage"
import { deviceWords } from "./device-words"

const RUN = { id: "run-5", approach: "device_users", status: "completed", progress: {}, error: null, counts: { by_kind: { shared_markers: 1 } },
  coverage: { sentence: "Records of the owner using the phone exist on all 2 phones." }, created_at: "2026-11-03T08:00:00Z", finished_at: "2026-11-03T08:01:00Z" }
const MARK = { id: "m1", kind: "shared_markers", strength: "strong", label: "Lead for enquiry", decision: null, decisions: [], period_start: null, period_end: null,
  measures: { phones: ["C1", "C2"], by_kind: { iccid: 1 } }, directions: { supports: [], undercuts: [] } }

describe("Who used which phone (AP-1, 05 8.8)", () => {
  it("lays out the parts and states what is not offered", async () => {
    client.runs.mockResolvedValue({ items: [RUN] })
    client.coverage.mockResolvedValue({ sentence: RUN.coverage.sentence })
    client.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [MARK] })
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/cases/c1/x"]}><Routes><Route path="/cases/:id/x" element={<DeviceUsersPage />} /></Routes></MemoryRouter>
      </QueryClientProvider>)
    const row = await screen.findByTestId("device-user-result")
    expect(Array.from(document.querySelectorAll("[data-part]")).map((e) => e.getAttribute("data-part"))).toEqual(["what", "run", "coverage", "results"])
    expect(screen.getByText(WHAT_IT_DOES)).toBeInTheDocument()
    expect(screen.getByText(NOT_BUILT)).toBeInTheDocument()
    expect(screen.getByTestId("device-user-result-total").textContent).toBe("1 result.")
    expect(within(row).getByText("Lead for enquiry")).toBeInTheDocument()
    expect(row).toHaveTextContent("C1 and C2 have 1 SIM card number in common")
  })

  it("words use in turn as numbers, never as who used the phone", () => {
    const w = deviceWords({ ...MARK, kind: "complementary_use", strength: "measured",
      measures: { phones: ["C1", "C2"], days: 14, both: 0, only_x: 168, only_y: 168, neither: 1008, phi: -0.14, switches_per_day: 1, first_day: "2023-01-02", last_day: "2023-01-15" } })
    expect(w.title).toBe("C1 and C2: 14 days with use on both")
    expect(JSON.stringify(w) + WHAT_IT_DOES).not.toMatch(/same person|used by one person|—|owner used/)
  })
})
