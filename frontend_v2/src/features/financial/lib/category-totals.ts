import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import type { LedgerTransaction } from "../api"
import { categoryName } from "../hooks/use-payment-categories"

export interface CategoryTotal {
  category: string
  currency: string
  moneyIn: bigint
  moneyOut: bigint
  count: number
}

/** Totals per category and currency for payments already on screen (a person's or name's own scope). */
export function categoryTotals(rows: LedgerTransaction[]): CategoryTotal[] {
  const totals = new Map<string, CategoryTotal>()
  for (const row of rows) {
    const category = categoryName(row)
    const key = `${row.currency}\u0000${category}`
    const total = totals.get(key) ?? { category, currency: row.currency, moneyIn: 0n, moneyOut: 0n, count: 0 }
    const amount = BigInt(row.amount_minor)
    if (row.direction === "credit") total.moneyIn += amount
    else if (row.direction === "debit") total.moneyOut += amount
    total.count += 1
    totals.set(key, total)
  }
  return sortTotals([...totals.values()])
}

function sortTotals(rows: CategoryTotal[]) {
  return rows.sort(
    (a, b) =>
      a.currency.localeCompare(b.currency) ||
      (b.moneyIn + b.moneyOut > a.moneyIn + a.moneyOut ? 1 : b.moneyIn + b.moneyOut < a.moneyIn + a.moneyOut ? -1 : 0)
  )
}

/** The case's stored category totals for one account or one saved statement, from the breakdown the main list uses. */
export function useScopedCategoryTotals(
  caseId: string,
  scope: { account_ids?: string[]; source_document_ids?: string[] }
) {
  return useQuery({
    queryKey: ["financial-ledger", caseId, "category-breakdown", "scoped", scope],
    queryFn: async () => {
      const result = await fetchAPI<{
        case_id: string
        rows: { category: string; currency: string; money_in_minor: string; money_out_minor: string; count: number }[]
      }>(`/api/financial/ledger/category-breakdown?${new URLSearchParams({ case_id: caseId })}`, {
        method: "POST",
        body: { group_by: "all", ...scope },
      })
      if (result.case_id !== caseId) throw Error("Category totals came from a different case.")
      return sortTotals(
        result.rows.map((row) => ({
          category: row.category,
          currency: row.currency,
          moneyIn: BigInt(row.money_in_minor),
          moneyOut: BigInt(row.money_out_minor),
          count: row.count,
        }))
      )
    },
    staleTime: 60_000,
  })
}

