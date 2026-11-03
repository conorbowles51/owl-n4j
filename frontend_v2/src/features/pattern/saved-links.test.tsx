import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { patternAPI, type Claim, type SavedCheck, type Snapshot, type SubjectList } from "./api"
import { PatternsPage } from "./components/PatternsPage"
import { dateIn, snapshotView } from "./lanes-lib"

// Saved phone_analysis and statement_check links (lx-collect phone-links.ts) open
// /cases/:id/phone-patterns?analysis=<kind>&snapshot=<id> and /cases/:id/phone-patterns?check=<id>.
// Before this, the page ignored both parameters and opened the first phone's Day view.

vi.mock("@/features/dossiers/api", () => ({ dossiersAPI: { list: vi.fn().mockResolvedValue({ dossiers: [], total: 0 }), get: vi.fn() } }))

const phone = (id: string, label: string) => ({
  kind: "extraction" as const, extraction_id: id, label, device_zone: null, first: null, last: "2023-03-20",
  projection_status: "ready", event_count: 1, usual_span: null,
})
const list: SubjectList = { extractions: [phone("e1", "Phone 1"), phone("e2", "Phone 2")], dossiers: [], total_extractions: 2, total_dossiers: 0 }

const claim: Claim = {
  id: "cl2", version: 2, status: "confirmed", status_words: "Confirmed by A. Person", kind: "inactive",
  subject: { kind: "extraction", extraction_id: "e2" }, window_start: "2023-03-14T23:00:00+00:00",
  window_end: "2023-03-15T06:00:00+00:00", window_zone: "UTC", window_text: "asleep from eleven", place: null,
  counterpart: null, origin: "manual", ai_model: null, missing_for_confirm: [],
}
const saved = {
  evaluation_id: "ev-old", claim_id: "cl2", claim_version: 2, evaluated_at: "2023-04-01T09:30:00+00:00",
  outcome: "consistent", outcome_basis: "data", outcome_words: "Consistent with the phone's records (saved check).",
  stale: false, window: { start: claim.window_start!, end: claim.window_end!, zone: "UTC" }, summary: {},
  counts: { contradicting: {}, supporting: {}, gap: 0, context: 0 }, total_items: 0, items: [], disputed_items: 0,
  claim, subject: claim.subject,
} as SavedCheck

const snap: Snapshot = {
  id: "s1", kind: "grid", label: "Pattern grid, Phone 2, 2023-03-01 05:00 to 2023-03-11 05:00 (America/New_York)",
  record_count: 42, stale: true, stale_words: "The phones' readings changed after this result was frozen; the frozen result is kept as it was.",
  created_by_name: "A. Person", created_at: "2023-04-02T10:00:00+00:00",
  snapshot: { summary_counts: { events: 42 }, window: { start: "2023-03-01T05:00:00+00:00", end: "2023-03-11T05:00:00+00:00", zone: "America/New_York" },
    subject: { kind: "extraction", extraction_id: "e2" } },
}

function show(path: string) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Routes><Route path="/cases/:id/phone-patterns" element={<PatternsPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("saved links open on the Patterns screen", () => {
  beforeEach(() => {
    vi.spyOn(patternAPI, "subjects").mockResolvedValue(list)
    vi.spyOn(patternAPI, "keyDates").mockResolvedValue({ total: 0, items: [] })
    vi.spyOn(patternAPI, "day").mockReturnValue(new Promise(() => {}))
    vi.spyOn(patternAPI, "grid").mockReturnValue(new Promise(() => {}))
  })
  afterEach(() => vi.restoreAllMocks())

  it("opens a saved statement check as it ran, on its statement's phone, not the latest check", async () => {
    vi.spyOn(patternAPI, "check").mockResolvedValue(saved)
    vi.spyOn(patternAPI, "claims").mockResolvedValue({ total: 1, items: [claim] })
    const evaluations = vi.spyOn(patternAPI, "evaluations").mockResolvedValue({ total: 2, items: [
      { evaluation_id: "ev-old", stale: false, outcome: "consistent" }, { evaluation_id: "ev-new", stale: false, outcome: "contradicted" }] })
    const evaluate = vi.spyOn(patternAPI, "evaluate")
    show("/cases/c1/phone-patterns?check=ev-old")
    expect(await screen.findByText("Consistent with the phone's records (saved check).")).toBeTruthy()
    expect(screen.getByText(/Opened from a saved link: this is the check as it ran at 2023-04-01 09:30 UTC/)).toBeTruthy()
    expect(patternAPI.check).toHaveBeenCalledWith("c1", "ev-old")
    expect((screen.getByLabelText("Phone or person") as HTMLSelectElement).value).toBe("e:e2")
    expect(screen.getByRole("button", { name: "Check a statement" }).getAttribute("aria-pressed")).toBe("true")
    expect(evaluations).not.toHaveBeenCalled()
    expect(evaluate).not.toHaveBeenCalled()
  })

  it("keeps the saved check when the statement was edited after it ran", async () => {
    vi.spyOn(patternAPI, "check").mockResolvedValue(saved)
    vi.spyOn(patternAPI, "claims").mockResolvedValue({ total: 1, items: [{ ...claim, version: 3 }] })
    const evaluations = vi.spyOn(patternAPI, "evaluations").mockResolvedValue({ total: 0, items: [] })
    const evaluate = vi.spyOn(patternAPI, "evaluate")
    show("/cases/c1/phone-patterns?check=ev-old")
    expect(await screen.findByText("Consistent with the phone's records (saved check).")).toBeTruthy()
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.getByText("Consistent with the phone's records (saved check).")).toBeTruthy()
    expect(evaluations).not.toHaveBeenCalled()
    expect(evaluate).not.toHaveBeenCalled()
  })

  it("says plainly when the saved check is not in this case", async () => {
    vi.spyOn(patternAPI, "check").mockRejectedValue(new Error("That check is not in this case."))
    vi.spyOn(patternAPI, "claims").mockResolvedValue({ total: 0, items: [] })
    show("/cases/c1/phone-patterns?check=nope")
    expect(await screen.findByText(/The saved statement check could not be opened/)).toBeTruthy()
  })

  it("opens a saved result: what was kept, that it changed since, and the same view on its phone and last day", async () => {
    vi.spyOn(patternAPI, "snapshot").mockResolvedValue(snap)
    show("/cases/c1/phone-patterns?analysis=grid&snapshot=s1")
    expect(await screen.findByText(/Saved result: Pattern grid, Phone 2/)).toBeTruthy()
    expect(screen.getByText(/42 records kept, saved by A. Person/)).toBeTruthy()
    expect(screen.getByText(/the frozen result is kept as it was/)).toBeTruthy()
    expect(screen.getByText(/as the phones read now, ending on 2023-03-10/)).toBeTruthy()
    expect((screen.getByLabelText("Phone or person") as HTMLSelectElement).value).toBe("e:e2")
    expect(screen.getByRole("button", { name: "Pattern grid" }).getAttribute("aria-pressed")).toBe("true")
    expect(patternAPI.grid).toHaveBeenCalledWith("c1", { kind: "extraction", extraction_id: "e2" }, "2023-02-11", "2023-03-10")
  })
})

describe("a saved result's last day is read in its own zone", () => {
  it("uses the zone the result was frozen in, and UTC for a zone the browser does not know", () => {
    expect(dateIn("2023-03-11T04:59:59.999Z", "America/New_York")).toBe("2023-03-10")
    expect(dateIn("2023-03-11T04:59:59.999Z", "device")).toBe("2023-03-11")
    expect(snapshotView({ ...snap, kind: "window" }).view).toBe("day")
  })
})
