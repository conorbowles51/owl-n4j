import { expect, it } from "vitest"
import { coverageMonths } from "./coverage-months"
it("reports two missing months out of 24 without counting duplicates twice", () => {
  const report = coverageMonths([
    { start: "2024-01-01", end: "2024-12-31" },
    { start: "2024-01-01", end: "2024-12-31" },
    { start: "2025-03-01", end: "2025-12-31" },
  ])!
  expect(report.months).toHaveLength(24)
  expect(
    report.months
      .filter((month) => month.status === "missing")
      .map((month) => month.month)
  ).toEqual(["2025-01", "2025-02"])
})
it("separates partially covered months from wholly missing months", () => {
  const report = coverageMonths([
    { start: "2024-01-20", end: "2024-02-10" },
    { start: "2024-02-12", end: "2024-03-05" },
  ])!
  expect(report.months.map((month) => month.status)).toEqual([
    "covered",
    "partial",
    "covered",
  ])
  expect(report.start).toBe("2024-01-20")
  expect(report.end).toBe("2024-03-05")
})
it("does not infer a time range from missing dates", () => {
  expect(coverageMonths([])).toBeNull()
})
