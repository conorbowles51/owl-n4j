import { describe, expect, it } from "vitest"
import { compareWords } from "./compare-words"

/** 05 15.8 on the screen. Invented data only. */
const r = (kind: string, strength: string, measures: Record<string, unknown>) => ({ kind, strength, measures }) as never
describe("Extraction comparison words", () => {
  it("states the identity verdict with the identifiers compared", () => {
    expect(compareWords(r("identity_check", "undetermined", { phones: ["C1", "C2"], equal: ["IMEI"], different: ["Serial"], app_jaccard: null })).title)
      .toBe("C1 (earlier) and C2 (later): cannot say from what the reports hold")
  })
  it("states a record's attribution", () => {
    expect(compareWords(r("only_in_later", "created_after_first", { phones: ["C1", "C2"], record_type: "InstantMessage", reason: "created_after_first" })).line)
      .toBe("Only in the later extraction: created after the first extraction. C1 (earlier) and C2 (later).")
  })
})
