import { renderHook } from "@testing-library/react"
import { expect, it } from "vitest"
import { useFilteredTransactions } from "./use-filtered-transactions"
import type { Transaction } from "../api"
const rows = Array.from(
  { length: 80 },
  (_, index) =>
    ({
      key: String(index),
      name: `Receipt ${index}`,
      amount: 100,
      currency: "EUR",
    }) as Transaction
)
const params = {
  searchQuery: "",
  selectedCategories: new Set<string>(),
  startDate: "",
  endDate: "",
  entityFilter: null,
  selectedFromEntities: new Set<string>(),
  selectedToEntities: new Set<string>(),
  minAmount: "",
  maxAmount: "",
  sortColumns: [],
  pageSize: 25,
  currentPage: 2,
}
it("keeps the table and page counter together when fewer records remain", () => {
  const current = renderHook(
    ({ transactions }) => useFilteredTransactions(transactions, params),
    { initialProps: { transactions: rows } }
  )
  expect(current.result.current.pageTransactions[0].key).toBe("50")
  current.rerender({ transactions: rows.slice(0, 30) })
  expect(current.result.current.currentPage).toBe(1)
  expect(current.result.current.pageTransactions.map((row) => row.key)).toEqual(
    ["25", "26", "27", "28", "29"]
  )
})
it("shows all rows on the single All page and handles an empty load without overwriting the requested page", () => {
  const current = renderHook(
    ({ transactions }) => useFilteredTransactions(transactions, params),
    { initialProps: { transactions: [] as Transaction[] } }
  )
  expect(current.result.current.currentPage).toBe(0)
  current.rerender({ transactions: rows })
  expect(current.result.current.currentPage).toBe(2)
  const all = renderHook(() =>
    useFilteredTransactions(rows, { ...params, pageSize: -1 })
  )
  expect(all.result.current.currentPage).toBe(0)
  expect(all.result.current.pageTransactions).toHaveLength(80)
})
