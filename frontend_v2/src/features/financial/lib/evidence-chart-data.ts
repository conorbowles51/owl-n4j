import type { Transaction } from "../api"
import { evidenceAmountCents } from "./evidence-amounts"
import { parseFinancialDate } from "./date-utils"

export type FinancialChartGrouping = "daily" | "weekly" | "monthly"

function getGroupKey(date: Date, grouping: FinancialChartGrouping): string {
  if (grouping === "monthly") {
    return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`
  }
  if (grouping === "weekly") {
    const d = new Date(date)
    d.setUTCDate(d.getUTCDate() - d.getUTCDay())
    return d.toISOString().slice(0, 10)
  }
  return date.toISOString().slice(0, 10)
}

export function buildEvidenceVolumeData(
  transactions: Transaction[],
  grouping: FinancialChartGrouping
) {
  const groups = new Map<string, Map<string, bigint>>()
  const categories = [
    ...new Set(transactions.map((row) => row.category || "Uncategorized")),
  ]
  for (const row of transactions) {
    const date = parseFinancialDate(row.date)
    const amount = evidenceAmountCents(row.amount)
    if (!date || amount === null) continue
    const key = getGroupKey(date, grouping)
    const group = groups.get(key) || new Map<string, bigint>()
    const category = row.category || "Uncategorized"
    group.set(
      category,
      (group.get(category) || 0n) + (amount < 0n ? -amount : amount)
    )
    groups.set(key, group)
  }
  const tooLarge = [...groups.values()].some(
    (group) =>
      [...group.values()].reduce((total, value) => total + value, 0n) >
      BigInt(Number.MAX_SAFE_INTEGER)
  )
  return {
    categories,
    tooLarge,
    data: tooLarge
      ? []
      : [...groups.entries()]
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([period, group]) => ({
            period,
            ...Object.fromEntries(
              categories.map((category, i) => [
                `category_${i}`,
                Number(group.get(category) || 0n) / 100,
              ])
            ),
          })),
  }
}
