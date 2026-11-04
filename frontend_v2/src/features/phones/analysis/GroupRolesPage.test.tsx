import { fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

/** 05 3.9 (AP-1) and 7.8 test 4 for approach 4 group roles; the analyses index. Invented data only. */
const client = vi.hoisted(() => ({
  runs: vi.fn(), request: vi.fn(), run: vi.fn(), cancel: vi.fn(), coverage: vi.fn(), results: vi.fn(), detail: vi.fn(), decide: vi.fn(),
}))
vi.mock("./analysis-api", () => ({ analysisAPI: () => client, keptResults: vi.fn().mockResolvedValue({ total: 0, offset: 0, limit: 50, items: [] }) }))
vi.mock("@/features/pattern/api", () => ({ patternAPI: { keyDates: vi.fn().mockResolvedValue({ total: 0, items: [] }) } }))
vi.mock("@/features/pattern/components/CollectBar", () => ({ CollectBar: () => <div>Add to…</div> }))

import GroupRolesPage, { WHAT_IT_DOES } from "./GroupRolesPage"
import { groupWords } from "./group-words"
import AnalysesPage from "./AnalysesPage"
import { ANALYSES } from "./analyses-list"

const NOTES = ["Owner read or play times on 0 of 1 phones; the read results below rest on 0 timed incoming messages (0 played), out of 74 incoming.",
  "Rule of thumb (no measurement behind it): the plan asked for owner read times on a fifth of incoming messages on 5 phones before comparing read times; 0 of 1 phones here meet it."]
const RUN = { id: "run-4", approach: "awareness", status: "completed", progress: {}, error: null, counts: { by_kind: { group_roles: 1 }, reply_latency_weak: 2, reply_latency_moderate: 1 },
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

describe("Reading, replies and group roles (AP-1, 05 7.8)", () => {
  it("lays out the parts, the coverage with the counts behind it, the total and the label", async () => {
    client.runs.mockResolvedValue({ items: [RUN] })
    client.coverage.mockResolvedValue({ sentence: RUN.coverage.sentence, notes: NOTES })
    client.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [GROUP] })
    mount("/cases/c1/phone-analyses/groups", <GroupRolesPage />, "/cases/:id/phone-analyses/groups")
    const row = await screen.findByTestId("group-result")
    expect(Array.from(document.querySelectorAll("[data-part]")).map((e) => e.getAttribute("data-part"))).toEqual(["what", "run", "coverage", "results"])
    expect(screen.getByText(WHAT_IT_DOES)).toBeInTheDocument()
    // cb-gated-aware D: the true counts and the plan's figure as a rule of thumb, never a switch that hides results
    for (const n of NOTES) expect(within(screen.getByTestId("group-result-notes")).getByText(n)).toBeInTheDocument()
    expect(screen.getByTestId("group-result-strengths").textContent).toBe("By strength: Read times: none; Reply times: 1 moderate, 2 weak; Read, no reply: none; Unread: none.")
    expect(screen.getByText(RUN.coverage.sentence)).toBeInTheDocument()
    expect(screen.getByTestId("group-result-total").textContent).toBe("1 result.")
    expect(within(row).getByText("Lead for enquiry")).toBeInTheDocument()
    expect(row).toHaveTextContent("Admin at extraction: Synthetic Person 2.")
    // 7.8.4: a change with no timestamp says its time is not recorded; the party is "participant named", never the actor
    expect(row).toHaveTextContent("participant left (time not recorded, participant named: Synthetic X)")
  })
})

describe("Read results words (05 7.3 steps 1 to 4)", () => {
  const base = { ...GROUP, id: "r1", period_start: null, period_end: null }
  it("puts the strength first and gives latency as median and middle half", () => {
    const w = groupWords({ ...base, kind: "reply_latency", strength: "weak",
      measures: { phone_label: "C1", title: null, correspondent: { display: "Synthetic Sender" }, latency: { n: 1, median_s: 1200, q1_s: 1200, q3_s: 1200 }, read_to_reply: { n: 1, median_s: 900, q1_s: 900, q3_s: 900 } } })
    expect(w.title).toBe("Weak. Reply times with Synthetic Sender on C1")
    expect(w.line).toBe("1 reply; median 20 minutes, middle half 20 minutes to 20 minutes. From the owner's read time: median 15 minutes over 1.")
  })
  it("words read with no reply and unread as counts", () => {
    expect(groupWords({ ...base, kind: "read_without_reply", strength: "faint",
      measures: { phone_label: "C1", correspondent: { display: "S" }, read_incoming: 4, without_reply: 1, window_hours: 48, window_basis: "parameter" } }).line)
      .toBe("1 of 4 messages the owner read had no message back within 48 hours.")
    expect(groupWords({ ...base, kind: "unread", strength: "weak", measures: { phone_label: "C1", correspondent: { display: "S" }, unread: 7 } }).title).toBe("Weak. Unread at extraction: S on C1")
  })
})

describe("Export from a result", () => {
  it("offers the export only when the result has records behind it", async () => {
    client.runs.mockResolvedValue({ items: [RUN] })
    client.coverage.mockResolvedValue({ sentence: RUN.coverage.sentence })
    client.results.mockResolvedValue({ total: 2, offset: 0, limit: 100, items: [GROUP, { ...GROUP, id: "g2" }] })
    client.detail.mockImplementation((_c: string, id: string) => Promise.resolve({ records: id === "g1" ? [] : [{ record_uid: "u1", role: "group" }] }))
    mount("/cases/c1/phone-analyses/groups", <GroupRolesPage />, "/cases/:id/phone-analyses/groups")
    const [none, some] = await screen.findAllByTestId("group-result")
    for (const row of [none, some]) fireEvent.click(within(row).getByRole("button", { expanded: false }))
    await within(none).findByText("0 records behind it.")
    await within(some).findByText("1 record behind it.")
    expect(within(none).queryByRole("button", { name: /^Export/ })).toBeNull()
    expect(within(some).getByRole("button", { name: "Export the messages and calls behind it…" })).toBeInTheDocument()
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
