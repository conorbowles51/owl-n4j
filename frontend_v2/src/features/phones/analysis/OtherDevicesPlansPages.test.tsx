import { render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactElement } from "react"
import { describe, expect, it, vi } from "vitest"

/** 05 3.9 (AP-1) for approaches 6 and 10, the thin-data line (cb-gated-spread E). Invented data only. */
const client = vi.hoisted(() => ({
  runs: vi.fn(), request: vi.fn(), run: vi.fn(), cancel: vi.fn(), coverage: vi.fn(), results: vi.fn(), detail: vi.fn(), decide: vi.fn(),
}))
vi.mock("./analysis-api", () => ({ analysisAPI: () => client }))
vi.mock("@/features/pattern/api", () => ({ patternAPI: { keyDates: vi.fn().mockResolvedValue({ total: 0, items: [] }) } }))
vi.mock("@/features/pattern/components/CollectBar", () => ({ CollectBar: () => <div>Add to…</div> }))

import OtherDevicesPage, { OLD_RULE as OD_OLD, WHAT_IT_DOES as OD_WHAT } from "./OtherDevicesPage"
import PlansPage, { OLD_RULE as PL_OLD } from "./PlansPage"
import { otherDevicesWords } from "./other-devices-words"
import { plansWords } from "./plans-words"

const base = { label: "Lead for enquiry", decision: null, decisions: [], period_start: null, period_end: null, directions: { supports: [], undercuts: [] } }

function show(el: ReactElement) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/cases/c1/x"]}><Routes><Route path="/cases/:id/x" element={el} /></Routes></MemoryRouter>
    </QueryClientProvider>)
}

describe("Devices and accounts across phones (AP-1, 05 9.8)", () => {
  it("lays out the parts, lists a moderate key and states the counts by strength", async () => {
    const run = { id: "r6", approach: "other_devices", status: "completed", progress: {}, error: null, created_at: null, finished_at: "2026-11-04T10:00:00Z",
      counts: { by_kind: { shared_key: 1 }, shared_strong: 0, shared_moderate: 1, shared_weak: 0, shared_faint: 0 }, coverage: { sentence: "WiFi networks exist on all 2 phones." } }
    const row = { ...base, id: "k1", kind: "shared_key", strength: "moderate",
      measures: { key_kind: "saved_login", value: null, phones: [{ phone_label: "C1", records: 1, events: 1, natures: [], nearby_only: false, first: null, last: null },
        { phone_label: "C2", records: 1, events: 1, natures: [], nearby_only: false, first: null, last: null }],
        reasons: { match: ["Same saved-login account on one service on 2 phones: moderate."], substantiation: ["Records or events behind it on each phone: 1, 1."] } } }
    client.runs.mockResolvedValue({ items: [run] })
    client.coverage.mockResolvedValue({ sentence: run.coverage.sentence })
    client.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [row] })
    show(<OtherDevicesPage />)
    const r = await screen.findByTestId("other-devices-result")
    expect(Array.from(document.querySelectorAll("[data-part]")).map((e) => e.getAttribute("data-part"))).toEqual(["what", "run", "coverage", "results"])
    expect(screen.getByText(OD_WHAT)).toBeInTheDocument()
    expect(within(r).getByText("Lead for enquiry")).toBeInTheDocument()
    expect(r).toHaveTextContent("Moderate: the same saved-login account on one service on C1 and C2")
    const line = screen.getByTestId("strength-line")
    expect(line).toHaveTextContent("1 key shared across phones in all: strong 0, moderate 1, weak 0, faint 0.")
    expect(line).toHaveTextContent(OD_OLD)
    expect(line).toHaveTextContent("rules of thumb")
  })

  it("words a detected-only peer as nearby, not connected", () => {
    const w = otherDevicesWords({ ...base, id: "k2", kind: "shared_key", strength: "faint",
      measures: { key_kind: "bluetooth_name", value: "Car Kit", phones: [{ phone_label: "C1", records: 1, events: 2, natures: ["Detected"], nearby_only: true, first: null, last: null },
        { phone_label: "C2", records: 1, events: 1, natures: ["Connected"], nearby_only: false, first: null, last: null }], reasons: { match: [], substantiation: [] } } })
    expect(w.title).toBe("Faint: the same Bluetooth device name Car Kit on C1 and C2")
    expect(w.line).toContain("C1: 2 records, nearby, not connected")
    expect(JSON.stringify(w)).not.toMatch(/—/)
  })
})

describe("Plans and check-ins against location (AP-1, 05 13.8)", () => {
  it("states the counts by strength and words a comparison", async () => {
    const run = { id: "r10", approach: "plans", status: "completed", progress: {}, error: null, created_at: null, finished_at: "2026-11-04T10:00:00Z",
      counts: { by_kind: { inconsistent: 1 }, by_strength_strong: 0, by_strength_moderate: 1, by_strength_weak: 0, by_strength_faint: 2 }, coverage: { sentence: "Calendar entries exist on all 1 phones." } }
    const row = { ...base, id: "p1", kind: "inconsistent", strength: "moderate",
      measures: { phone_label: "C1", source: "checkin", start: "2023-03-04T15:00:00+00:00", reasons: { match: ["Inconsistent: 0 of 1 location records in the window are within the two radii."], substantiation: [] } } }
    client.runs.mockResolvedValue({ items: [run] })
    client.coverage.mockResolvedValue({ sentence: run.coverage.sentence })
    client.results.mockResolvedValue({ total: 1, offset: 0, limit: 100, items: [row] })
    show(<PlansPage />)
    const r = await screen.findByTestId("plans-result")
    expect(r).toHaveTextContent("Moderate: Check-in on C1")
    expect(r).toHaveTextContent("Inconsistent: 0 of 1")
    expect(screen.getByTestId("strength-line")).toHaveTextContent("3 entries, check-ins and notes in all: strong 0, moderate 1, weak 0, faint 2.")
    expect(screen.getByTestId("strength-line")).toHaveTextContent(PL_OLD)
  })

  it("writes the entry's time with the app's formatter, not the raw timestamp", () => {
    const w = plansWords({ ...base, id: "p3", kind: "no_place", strength: "faint",
      measures: { phone_label: "C1", source: "calendar", subject: "Lunch", start: "2024-01-20T03:51:51.117000+00:00", reasons: { match: [], substantiation: [] } } })
    expect(w.when).toBe("Sat, Jan 20, 2024, 3:51:51 AM UTC")
    const wall = plansWords({ ...base, id: "p4", kind: "no_place", strength: "faint",
      measures: { phone_label: "C1", source: "calendar", subject: "Lunch", start: "2024-01-20T03:51:51", reasons: { match: [], substantiation: [] } } })
    expect(wall.when).toBe("Sat, Jan 20, 2024, 3:51:51 AM, no offset in report")
    const repeats = plansWords({ ...base, id: "p5", kind: "no_place", strength: "faint",
      measures: { phone_label: "C1", source: "calendar", subject: "Lunch", occurrences: 3, repeat_rule: "Daily", last_occurrence: "2024-02-06T03:51:51.117000+00:00", reasons: { match: [], substantiation: [] } } })
    expect(repeats.line).toContain("the last Tue, Feb 6, 2024, 3:51:51 AM UTC.")
  })

  it("words a repeating unplaced entry with its occurrences", () => {
    const w = plansWords({ ...base, id: "p2", kind: "no_place", strength: "faint",
      measures: { phone_label: "C1", source: "calendar", subject: "Weekly", occurrences: 5, repeat_rule: "Weekly", last_occurrence: "2023-01-30", occurrence_count: 1, reasons: { match: ["No place is recorded, so nothing is compared."], substantiation: [] } } })
    expect(w.title).toBe("Faint: Calendar entry on C1: Weekly")
    expect(w.line).toContain("Repeats weekly: 5 occurrences")
  })
})
