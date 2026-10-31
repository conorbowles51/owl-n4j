import type { LedgerOverviewTotals } from "../api"

/**
 * The Overview's top-card figures from the server's totals, ordered as the page orders them: currencies by
 * payments, most first, then by the browser's text order. ``money`` per currency: money in (credit) and out.
 */
export function overviewFigures(totals: LedgerOverviewTotals | undefined) {
  const currencyCounts = new Map<string, number>()
  const money = new Map<string, { credit: bigint; debit: bigint }>()
  for (const entry of totals?.currencies ?? []) {
    currencyCounts.set(entry.currency, entry.payments)
    money.set(entry.currency, { credit: BigInt(entry.credit), debit: BigInt(entry.debit) })
  }
  const currencies = [...currencyCounts.keys()].sort(
    (a, b) => (currencyCounts.get(b) ?? 0) - (currencyCounts.get(a) ?? 0) || a.localeCompare(b)
  )
  return {
    payments: totals?.payments ?? 0,
    unknownDates: totals?.unknown_dates ?? 0,
    uncategorised: totals?.uncategorised ?? 0,
    accountCount: totals?.accounts ?? 0,
    firstDay: totals?.first_day ?? null,
    lastDay: totals?.last_day ?? null,
    currencyCounts,
    currencies,
    money,
  }
}
