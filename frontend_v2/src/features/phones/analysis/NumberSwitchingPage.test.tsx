import { describe, expect, it } from "vitest"
import { switchWords } from "./switch-words"

/** 05 16c.8 on the screen: the pair, the gap, the shared counterparts, and that nothing is joined. Invented data only. */
describe("Possible number changes words", () => {
  it("states the pair and says nothing is joined", () => {
    const w = switchWords({ measures: { from_display: "+1 202-555-0111", to_display: "+1 202-555-0122", last_of_first: "2023-01-31T12:00:00Z",
      first_of_second: "2023-02-05T12:00:00Z", gap_days: 5, similarity: 0.875, shared: 7, first_counterparts: 8, second_counterparts: 7, markers: ["never_same_day"] } } as never)
    expect(w.title).toBe("+1 202-555-0111 stops, +1 202-555-0122 starts 5 days later")
    expect(w.line).toContain("7 shared counterparts (8 before, 7 after; similarity 0.875).")
    expect(w.line).toContain("Also: never active on the same day.")
    expect(w.line).toContain("Nothing is joined")
  })

  it("states the strength and why", () => {
    const w = switchWords({ measures: { from_display: "a", to_display: "b", last_of_first: "2023-01-31T12:00:00Z", first_of_second: "2023-02-05T12:00:00Z",
      gap_days: 5, similarity: 0.4, shared: 2, first_counterparts: 2, second_counterparts: 5, markers: [], level: "faint", shared_besides_owners: 1,
      strength_reasons: { match: ["2 shared counterparts, 1 besides the phones' owners (similarity 0.40)", "under similarity 0.50 or 5 shared"], substantiation: [] } } } as never)
    expect(w.line.startsWith("Faint: 2 shared counterparts, 1 besides the phones' owners")).toBe(true)
  })
})
