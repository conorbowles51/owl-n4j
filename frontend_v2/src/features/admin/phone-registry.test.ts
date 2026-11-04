import { describe, expect, it } from "vitest"
import { flagActions, flagSubjectWords, rangeWords, readingWords } from "./phone-registry"

describe("phone registry words", () => {
  it("offers the 02 3.4 transitions a person may make, never mapped", () => {
    const to = (s: Parameters<typeof flagActions>[0]) => flagActions(s).map((a) => a.to)
    expect(to("open")).toEqual(["acknowledged", "mapping_needed", "dismissed"])
    expect(to("acknowledged")).toEqual(["open", "dismissed"])
    expect(to("dismissed")).toEqual(["open"])
    expect(to("mapping_needed")).toEqual(["dismissed"])
    expect(to("mapped")).toEqual(["dismissed"])
    for (const s of ["open", "acknowledged", "dismissed", "mapping_needed", "mapped"] as const)
      expect(to(s)).not.toContain("mapped")
  })

  it("states the range and the true total, never a page as the whole", () => {
    expect(rangeWords(0, 100, 500)).toBe("Showing 1 to 100 of 500")
    expect(rangeWords(400, 100, 500)).toBe("Showing 401 to 500 of 500")
    expect(rangeWords(0, 0, 0)).toBe("None")
  })

  it("names what a flag is about", () => {
    expect(flagSubjectWords({ flag_kind: "new_set_value", subject: { set: "ModelDirections", value: "Sideways" }, detail: {} }))
      .toBe("ModelDirections: Sideways")
    expect(flagSubjectWords({ flag_kind: "new_field", subject: { type: "Call", field: "Zz", value_type: "String" }, detail: {} }))
      .toBe("Call · Zz (String)")
    expect(flagSubjectWords({ flag_kind: "new_value_type", subject: { type: "Call", field: "Duration" },
      detail: { previous: ["TimeSpan"], now: "Int32" } })).toBe("Call · Duration (was TimeSpan, now Int32)")
    expect(flagSubjectWords({ flag_kind: "set_overflow", subject: { set: "Big", value: null }, detail: {} })).toBe("Big")
  })

  it("reads a reading as words", () => {
    expect(readingWords("TimeStamp")).toBe("TimeStamp")
    expect(readingWords({ semantics: "last_activity", meaning: "When it was last used" })).toBe("When it was last used")
    expect(readingWords(null)).toBe("Not set")
  })
})
