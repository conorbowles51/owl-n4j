import { describe, expect, it } from "vitest"
import { holdText, mismatchText, scanText } from "./file-check"

const file = { original_filename: "invoice.pdf" }

describe("file check words", () => {
  it("says nothing about a file that matches", () => {
    expect(mismatchText({ ...file, file_type_match: "match" })).toBeNull()
    expect(holdText(file)).toBeNull()
    expect(scanText({ ...file, malware_scan: "clean" })).toBeNull()
  })

  it("names what a mislabelled file holds", () => {
    expect(mismatchText({ ...file, file_type_match: "mismatch", file_type_words: "Windows program" }))
      .toBe("The name invoice.pdf does not match its contents, which are a Windows program. The file is kept as it arrived.")
  })

  it("states a hold and keeps the reason after a release", () => {
    expect(holdText({ ...file, reading_hold: "held", reading_hold_reason: "executable", file_type_words: "Linux program" }))
      .toContain("not sent for reading until someone releases it")
    expect(holdText({ ...file, reading_hold: "released", reading_hold_reason: "malware", reading_hold_detail: "Bad-Thing",
      reading_released_by: "A Person" })).toContain("found Bad-Thing. A Person released it")
  })

  it("never lets an unfinished scan read as clean", () => {
    expect(scanText({ ...file, malware_scan: "failed" })).toContain("not known to be clean")
  })
})
