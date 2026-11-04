import { describe, expect, it } from "vitest"
import { clockPeriodWords, clockRequest, offsetAmountWords } from "./setup-words"

describe("clock offset words", () => {
  it("a fast clock moves times back, and the last day is included", () => {
    expect(clockRequest("fast", "2", "", "2023-03-14", "2023-03-14")).toEqual({ seconds: -120, start: "2023-03-14T00:00:00Z", end: "2023-03-15T00:00:00Z" })
    expect(clockRequest("slow", "", "30", "", "")).toEqual({ seconds: 30, start: null, end: null })
    expect(clockRequest("fast", "", "", "", "")).toBeNull()
  })
  it("says which way the clock ran", () => {
    expect(offsetAmountWords(-120)).toBe("Clock ran fast by 2 minutes")
    expect(offsetAmountWords(3661)).toBe("Clock ran slow by 1 hour, 1 minute, 1 second")
    expect(clockPeriodWords(null, null)).toBe("for the whole phone")
  })
})
