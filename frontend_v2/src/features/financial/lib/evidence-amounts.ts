import type { Transaction } from "../api"

// These older evidence amounts are supplied at two decimal places. Refuse to
// turn an unsafe Number into an apparently exact total.
export function evidenceAmountCents(amount: number): bigint | null {
  if (
    !Number.isFinite(amount) ||
    !Number.isSafeInteger(Math.round(amount * 100))
  )
    return null
  if (Number(amount.toFixed(2)) !== amount) return null
  return BigInt(amount.toFixed(2).replace(".", ""))
}
export function formatEvidenceCents(value: bigint): string {
  const absolute = value < 0n ? -value : value
  return `${value < 0n ? "-" : ""}${(absolute / 100n).toLocaleString("en-IE")}.${String(absolute % 100n).padStart(2, "0")}`
}
export function evidenceCurrency(value: string | undefined): string | null {
  const currency = typeof value === "string" ? value.trim().toUpperCase() : null
  return currency && /^[A-Z]{3}$/.test(currency) ? currency : null
}
export function summarizeEvidenceAmounts(records: Transaction[]) {
  const groups = new Map<
    string,
    {
      currency: string
      count: number
      positive: bigint
      negative: bigint
      incomplete: boolean
    }
  >()
  for (const record of records) {
    const known = evidenceCurrency(record.currency)
    const currency =
      known ||
      (typeof record.currency === "string" ? record.currency.trim() : "") ||
      "Currency not recorded"
    const group = groups.get(currency) || {
      currency,
      count: 0,
      positive: 0n,
      negative: 0n,
      incomplete: !known,
    }
    group.count++
    const cents = evidenceAmountCents(record.amount)
    if (cents === null) group.incomplete = true
    else if (cents < 0n) group.negative += cents
    else group.positive += cents
    groups.set(currency, group)
  }
  return [...groups.values()].sort((a, b) =>
    a.currency.localeCompare(b.currency)
  )
}
