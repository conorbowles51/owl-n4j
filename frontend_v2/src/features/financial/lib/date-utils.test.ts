import { expect, it } from "vitest"
import { financialDateDay, formatFinancialDate } from "./date-utils"
import { filterTransactionsBase } from "./filter-transactions"
import type { Transaction } from "../api"

it("keeps the recorded calendar day regardless of timezone or locale", () => {
  expect(financialDateDay("2026-09-02T23:59:59-04:00")).toBe("2026-09-02")
  expect(formatFinancialDate("2026-09-02T00:10:00+03:00")).toBe("2026-09-02")
  expect(financialDateDay("2024-02-29")).toBe("2024-02-29")
})
it.each([
  "2026-02-30",
  "2026-02-29",
  "2026-09",
  "Sep 29",
  "09/02/2026",
  "2026-09-02T24:00",
  "0000-01-01",
])("does not invent a date from %s", (value) => {
  expect(financialDateDay(value)).toBeNull()
  expect(formatFinancialDate(value)).toBe(`${value} (check date)`)
})
it("includes every time on the chosen last day and keeps unresolved dates outside an active date filter", () => {
  const dates = [
    "2026-09-01",
    "2026-09-02",
    "2026-09-02T23:59:59-04:00",
    "2026-09-03",
    "Sep 2",
    "2026-02-30",
  ]
  const rows = dates.map(
    (date, i) =>
      ({
        key: String(i),
        date,
        amount: 100,
        from_entity: { key: null, name: null },
        to_entity: { key: null, name: null },
        financial_record_kind: "allegation",
        financial_view_mode: "intelligence",
        is_financial_event: true,
        is_evidence_backed_transaction: false,
      }) as Transaction
  )
  const filters = {
    searchQuery: "",
    selectedCategories: new Set<string>(),
    startDate: "2026-09-02",
    endDate: "2026-09-02",
    entityFilter: null,
    minAmount: "",
    maxAmount: "",
    sortColumns: [],
  }
  expect(filterTransactionsBase(rows, filters).map((row) => row.key)).toEqual([
    "1",
    "2",
  ])
  expect(
    filterTransactionsBase(rows, { ...filters, startDate: "", endDate: "" })
  ).toHaveLength(6)
})
