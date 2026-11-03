import { render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 05 3.9 (AP-1) and 7.8 test 4 for approach 4 group roles; the analyses index. Invented data only. */
const client = vi.hoisted(() => ({
  runs: vi.fn(), request: vi.fn(), run: vi.fn(), cancel: vi.fn(), coverage: vi.fn(), results: vi.fn(), detail: vi.fn(), decide: vi.fn(),
}))
vi.mock("./analysis-api", () => ({ analysisAPI: () => client }))
vi.mock("@/features/pattern/api", () => ({ patternAPI: { keyDates: vi.fn().mockResolvedValue({ total: 0, items: [] }) } }))
vi.mock("@/features/pattern/components/CollectBar", () => ({ CollectBar: () => <div>Add to…</div> }))

import GroupRolesPage, { NOT_BUILT, WHAT_IT_DOES } from "./GroupRolesPage"
import AnalysesPage from "./AnalysesPage"
import { ANALYSES } from "./analyses-list"

const RUN = { id: "run-4", approach: "awareness", status: "completed", progress: {}, error: null, counts: { by_kind: { group_roles: 1 } },
  coverage: { sentence: "Group chats exist on all 1 phones. Group admin flags exist on all 1 phones. Recorded membership changes exist on all 1 phones." },
  created_at: "2026-11-03T08:00:00Z", finished_at: "2026-11-03T08:01:00Z" }
const GROUP = {
  id: "g1", kind: "group_roles", strength: "timed", label: "Lead for enquiry", decision: null, decisions: [],
  period_start: "2023-05-01T10:00:00Z", period_end: "2023-05-01T10:00:00Z",
  measures: { phone_label: "C1", title: null, participants: 4, admins: [{ identity_key: null, display: "Synthetic Person 2" }],
    changes: [{ action: "ParticipantAdded", instant: "2023-05-01T10:00:00Z", participants: ["Synthetic Person 3"] },
      { action: "ParticipantLeft", instant: null, participants: ["Synthetic X"] }], timed_changes: 1 },
  directions: { supports: [], undercuts: [] },
}

function mount(path: string, el: React.ReactNode, route: string) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}><Routes><Route path={route} element={el} /></Routes></MemoryRouter>
    </QueryClientProvider>)
}

describe("Group admins and membership (AP-1, 05 7.8)", () => {
  it("lays out the parts, the coverage, the total and the label, and says what is not built", async () => {
    client.runs.mockResolvedValue({ items: [RUN] })
    client.coverage.mockResolvedValue({ sentence: RUN.coverage.sentence })
    client.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [GROUP] })
    mount("/cases/c1/phone-analyses/groups", <GroupRolesPage />, "/cases/:id/phone-analyses/groups")
    const row = await screen.findByTestId("group-result")
    expect(Array.from(document.querySelectorAll("[data-part]")).map((e) => e.getAttribute("data-part"))).toEqual(["what", "run", "coverage", "results"])
    expect(screen.getByText(WHAT_IT_DOES)).toBeInTheDocument()
    expect(screen.getByText(NOT_BUILT)).toBeInTheDocument()
    expect(screen.getByText(RUN.coverage.sentence)).toBeInTheDocument()
    expect(screen.getByTestId("group-result-total").textContent).toBe("1 result.")
    expect(within(row).getByText("Lead for enquiry")).toBeInTheDocument()
    expect(row).toHaveTextContent("Admin at extraction: Synthetic Person 2.")
    // 7.8.4: a change with no timestamp says its time is not recorded; the party is "participant named", never the actor
    expect(row).toHaveTextContent("participant left (time not recorded, participant named: Synthetic X)")
  })
})

describe("Phone analyses index", () => {
  it("links every built analysis and states the ones not built with the measured reason", () => {
    mount("/cases/c1/phone-analyses", <AnalysesPage />, "/cases/:id/phone-analyses")
    for (const a of ANALYSES) expect(screen.getByRole("link", { name: a.title })).toHaveAttribute("href", `/cases/c1/${a.path}`)
    expect(within(screen.getByRole("region", { name: "Not built" })).getAllByRole("listitem").length).toBeGreaterThan(0)
    expect(document.body.textContent).not.toMatch(/—/)
  })
})
