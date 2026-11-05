import { describe, expect, it } from "vitest"
import { isSizeRefusal, isTraceSizeRefusal, opensWholeCaseRun } from "./whole-case-run"

describe("isSizeRefusal", () => {
  it.each([
    "More than 500 current rows match. Narrow the date scope; no partial transfer comparison was made.",
    "More than 1,000 transfer candidates match. Narrow the date scope; no truncated comparison was returned.",
    "More than 1,000 identifier comparisons. Narrow the date scope; no partial comparison was returned.",
    "More than 1,000 payments match these filters. Choose an account or a shorter date range, then run this check again.",
    "More than 200 screening candidates match. Narrow the account or dates; no partial result was returned.",
    "More than 50 payments share one recorded name. Narrow the dates to inspect that relationship; no partial result was returned.",
    "A threshold candidate contains more than 50 readings. Narrow the dates or window; no partial result was returned.",
    "More than10,000candidate path extensions. Narrow the dates; no partial screen was returned.",
  ])("a size refusal opens the whole-case run: %s", (message) => {
    expect(isSizeRefusal(message)).toBe(true)
  })
  it.each([
    "Choose working or verified readings and a date tolerance from 0 to 7 days.",
    "Transfer review requires a consistent captured ledger and history.",
    "More than one possible match.",
    undefined,
  ])("any other refusal stays as it is: %s", (message) => {
    expect(isSizeRefusal(message)).toBe(false)
  })
})

describe("opensWholeCaseRun", () => {
  it("does not count a size refusal as a failed read", () => {
    expect(opensWholeCaseRun("More than 500 current rows match. Narrow the date scope; no partial transfer comparison was made.")).toBe(true)
    expect(opensWholeCaseRun("PDF reports support up to 2,000 readings.")).toBe(true)
  })
  it("keeps a real failure a failure", () => {
    expect(opensWholeCaseRun("Server error")).toBe(false)
    expect(opensWholeCaseRun(null)).toBe(false)
  })
})

describe("isTraceSizeRefusal", () => {
  it("opens the step trace when a case is too large to capture for one answer", () => {
    expect(isTraceSizeRefusal("The complete ledger record exceeds 64 MiB. Choose one account or a shorter date range to export. No partial export was produced.")).toBe(true)
  })
})
