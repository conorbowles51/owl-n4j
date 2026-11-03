import { describe, expect, it } from "vitest"
import { matrixWords } from "./matrix-words"

/** 05 16b.8 test 1 on the screen: calls by status, never summed into contact; the other direction as a count. */
describe("Who contacts whom words", () => {
  it("states each channel, calls by status and the other direction", () => {
    const w = matrixWords({ measures: { from_display: "Synthetic Y", to_display: "Owner of C1", total: 2, by_channel: { call: 2 },
      calls_by_status: { Established: 1, Missed: 1 }, connected_call_seconds: 60, reverse_total: 3, unmatched_owner_copies: 0 } } as never)
    expect(w.title).toBe("From Synthetic Y to Owner of C1: 2 calls")
    expect(w.line).toBe("Calls: 1 connected, 1 missed; 1 minute connected. In the other direction: 3.")
  })
  it("never shows a raw status code (seen live: \"1 Unknown\")", () => {
    const w = matrixWords({ measures: { from_display: "A", to_display: "B", total: 1, by_channel: { call: 1 }, calls_by_status: { Unknown: 1 },
      connected_call_seconds: 0, reverse_total: 0, unmatched_owner_copies: 0 } } as never)
    expect(w.line).toBe("Calls: 1 status not recorded. In the other direction: 0.")
  })
})
