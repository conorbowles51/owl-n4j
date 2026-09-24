import { expect, it } from "vitest"
import { statementMonth } from "./statement-month"

it("uses calendar month boundaries including leap and century years", () => {
  expect(statementMonth("2026-02")).toEqual({
    period_start: "2026-02-01",
    period_end: "2026-02-28",
  })
  expect(statementMonth("2024-02")?.period_end).toBe("2024-02-29")
  expect(statementMonth("2000-02")?.period_end).toBe("2000-02-29")
  expect(statementMonth("2100-02")?.period_end).toBe("2100-02-28")
  expect(statementMonth("2026-04")?.period_end).toBe("2026-04-30")
  expect(statementMonth("2026-12")?.period_end).toBe("2026-12-31")
  for (const invalid of ["", "2026-00", "2026-13", "0000-01", "2026-1"])
    expect(statementMonth(invalid)).toBeNull()
})
