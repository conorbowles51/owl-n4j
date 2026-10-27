import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen, within } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import type { LedgerTransaction } from "../api"
import { categoryTotals } from "../lib/category-totals"
import { CategoryBreakdownTable, ScopedCategoryBreakdown } from "./ScopedCategoryBreakdown"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
afterEach(cleanup)

it("asks for one account's stored category totals and shows every number as text per currency", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    case_id: "case",
    rows: [
      { category: "Transfers", currency: "MXN", money_in_minor: "1417500000", money_out_minor: "0", count: 2, group_key: "", group_label: "" },
      { category: "Uncategorized", currency: "MXN", money_in_minor: "0", money_out_minor: "5000", count: 1, group_key: "", group_label: "" },
    ],
  })
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ScopedCategoryBreakdown caseId="case" title="Categories in this account" scope={{ account_ids: ["acct"] }} />
    </QueryClientProvider>
  )
  const table = await screen.findByRole("table", { name: "Categories in this account · MXN" })
  const rows = within(table).getAllByRole("row").slice(1).map((row) => row.textContent)
  expect(rows).toEqual(["Transfers14,175,000.000.002", "Uncategorized0.0050.001"])
  expect(vi.mocked(fetchAPI).mock.calls[0][1]).toMatchObject({ method: "POST", body: { group_by: "all", account_ids: ["acct"] } })
})

it("adds up the payments on screen by category, keeping currencies apart", () => {
  const row = (amount: string, direction: string, currency: string, category?: string) =>
    ({ amount_minor: amount, direction, currency, category }) as unknown as LedgerTransaction
  const totals = categoryTotals([row("100", "credit", "USD", "Payroll"), row("40", "debit", "USD", "Payroll"), row("7", "debit", "EUR")])
  expect(totals).toEqual([
    { category: "Uncategorized", currency: "EUR", moneyIn: 0n, moneyOut: 7n, count: 1 },
    { category: "Payroll", currency: "USD", moneyIn: 100n, moneyOut: 40n, count: 2 },
  ])
  render(<CategoryBreakdownTable title="Categories in these payments" rows={totals} />)
  expect(screen.getByRole("table", { name: "Categories in these payments · USD" })).toHaveTextContent("Payroll1.000.402")
})
