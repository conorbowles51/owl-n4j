import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { ResultView } from "./ResultView"
import { Trail } from "./Trail"
import type { Corroboration } from "./result-types"

const lanes = vi.fn()
const trail = vi.fn()
vi.mock("@/features/relations/api", () => ({ relationAPI: { lanes: (...a: unknown[]) => lanes(...a), trail: (...a: unknown[]) => trail(...a) } }))

const c: Corroboration = {
  schema: "loupe.corroborate/1",
  question: { kind: "every_time", text: "Do they follow the same pattern every time?", chips: {} },
  level: { key: "strong", name: "Strong link", sentence: "3 of 3.", reasons: [], rule: "r" },
  comparison: { kind: "same_weekday_hours", words: "w", incident: [{ id: "i1", label: "Fri 3 May", start: "", end: "" }], ordinary: [] },
  grid: [{ signal: "s", link_kind: "contact", label: "A texts B", cells: { i1: "present" }, incident: { present: 1, of: 1 }, ordinary: { present: 0, of: 0 }, weight: "full", separates: true, records: { i1: ["phone_record:9"] } }],
  checks: [], people: [], not_in_pattern: [], gaps: [], look_further: [],
}
const wrap = (ui: React.ReactNode) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
)

describe("story lanes and trail", () => {
  it("opens one lane per person for an instance from the grid, events numbered", async () => {
    lanes.mockResolvedValue({ instance: { id: "i1", label: "Fri 3 May" }, events: 2, cited: 2, not_laid_out: [],
      lanes: [{ person: "p1", label: "Ann", events: [{ n: 1, ref: "phone_record:9", kind: "message", kind_words: "Message", at: "2024-05-03T22:00:00+00:00", day_only: false, text: "hello", with: ["Bob"] }] },
        { person: "p2", label: "Bob", events: [{ n: 2, ref: "financial_transaction:1", kind: "payment", kind_words: "Payment", at: "2024-05-04T00:00:00+00:00", day_only: true, text: "$400", with: [] }] }] })
    render(wrap(<ResultView c={c} caseId="c1" runId="r1" />))
    fireEvent.click(screen.getByRole("button", { name: /Open the story of incident/ }))
    expect(await screen.findByText("Ann")).toBeTruthy()
    expect(screen.getByLabelText("Event 2")).toBeTruthy()
    expect(screen.getByText(/with Bob/)).toBeTruthy()
    expect(lanes).toHaveBeenCalledWith("c1", "r1", "i1")
  })

  it("shows each build-out step with what it added and says when a step added nothing", async () => {
    trail.mockResolvedValue({ current: "b", steps: [
      { n: 1, selection_id: "a", members: 2, added: [], added_count: 2, level: { run_id: "x", key: "possible", name: "Possible link" }, level_moved: null, adds_nothing: false, created_at: null },
      { n: 2, selection_id: "b", members: 2, added: [], added_count: 0, level: { run_id: "y", key: "possible", name: "Possible link" }, level_moved: "unchanged", adds_nothing: true, created_at: null }] })
    render(wrap(<Trail caseId="c1" selectionId="b" />))
    expect(await screen.findByText(/added nothing/)).toBeTruthy()
    expect(screen.getByText(/started with 2 items/)).toBeTruthy()
    expect(screen.getByRole("link", { name: /without the later ones/ })).toBeTruthy()
  })
})
