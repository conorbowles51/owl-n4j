import { describe, expect, it } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { ResultView } from "./ResultView"
import type { Corroboration } from "./result-types"

const c: Corroboration = {
  schema: "loupe.corroborate/1",
  question: { kind: "in_contact", text: "Were they in contact on these nights?", chips: {} },
  level: { key: "strong", name: "Strong link", sentence: "Contact on 3 of 3 nights, 0 of 4 ordinary.", reasons: ["Contact: 3 of 3 nights."], rule: "r" },
  comparison: { kind: "same_weekday_hours", words: "Same hours on other Fridays", incident: [{ id: "i1", label: "Fri 3 May", start: "", end: "" }], ordinary: [{ id: "o1", label: "Fri 10 May", start: "", end: "" }] },
  grid: [{ signal: "contact:a", link_kind: "contact", label: "Kell texts Okafor", cells: { i1: "present", o1: "no_data" }, incident: { present: 1, of: 1 }, ordinary: { present: 0, of: 0 }, weight: "full", separates: true, records: { i1: ["phone_record:9"] } }],
  checks: [{ check: "busy_place", outcome: "ruled_out", words: "Not a busy place.", records: [] }],
  people: [], not_in_pattern: [{ who: "Mateo Ruiz", says: "No link found.", searched: ["contact on 1 night"] }],
  gaps: [], look_further: [],
}

describe("Corroborate result", () => {
  it("shows the level first, the grid with no-data apart from absent, every check, and the search behind a no-link", () => {
    render(<ResultView c={c} />)
    expect(screen.getByText("Strong link")).toBeTruthy()
    expect(screen.getByLabelText("No data")).toBeTruthy()
    expect(screen.getByText(/Ruled out/)).toBeTruthy()
    expect(screen.getByText(/Searched: contact on 1 night/)).toBeTruthy()
    fireEvent.click(screen.getByText("●"))
    expect(screen.getByText("phone_record:9")).toBeTruthy()
  })
})
