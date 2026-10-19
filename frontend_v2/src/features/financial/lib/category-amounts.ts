import type { LedgerTransaction } from "../api"
import { categoryName } from "../hooks/use-payment-categories"
import { minorAmount, paymentGroup } from "./investigator-workspace"

export function categoryAmounts(rows: LedgerTransaction[]) {
  const groups = new Map<
    string,
    {
      category: string
      currency: string
      card: boolean
      credit: bigint
      debit: bigint
      rows: LedgerTransaction[]
    }
  >()
  for (const row of rows) {
    const category = categoryName(row)
    const key = JSON.stringify([paymentGroup(row), category])
    const group = groups.get(key) ?? {
      category,
      currency: row.currency,
      card: row.account_type === "credit_card",
      credit: 0n,
      debit: 0n,
      rows: [],
    }
    group.rows.push(row)
    const amount = minorAmount(row.amount_minor)
    if (
      amount !== null &&
      amount >= 0 &&
      (row.direction === "credit" || row.direction === "debit")
    )
      group[row.direction] += amount
    groups.set(key, group)
  }
  return [...groups.values()].sort(
    (a, b) =>
      a.currency.localeCompare(b.currency) ||
      Number(a.card) - Number(b.card) ||
      a.category.localeCompare(b.category)
  )
}
