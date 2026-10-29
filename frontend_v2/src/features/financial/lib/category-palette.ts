import type { LedgerTransaction } from "../api"
import { currencyMinorUnits } from "./ledger-format"
import { paymentDay } from "./investigator-workspace"

/** dot / tint / text for a category chip or tile (FINANCIAL-DESIGN-SPEC tokens). */
export interface CategoryTone {
  dot: string
  tint: string
  text: string
}

const SPEC: Record<string, CategoryTone> = {
  transfers: { dot: "#3a6fd8", tint: "#e8effd", text: "#1d4aa6" },
  payroll: { dot: "#0f8a7e", tint: "#e0f4f1", text: "#0b6359" },
  taxes: { dot: "#7b52c7", tint: "#efe9fb", text: "#573199" },
  "rent and leases": { dot: "#c67a10", tint: "#fcf1df", text: "#7f4b09" },
  "bank fees": { dot: "#c4456b", tint: "#fbe8ee", text: "#932848" },
  payments: { dot: "#4b5bd6", tint: "#eaecfc", text: "#313fa8" },
  deposits: { dot: "#2f9353", tint: "#e4f4e9", text: "#1d6a3a" },
  "interest income": { dot: "#1789a6", tint: "#e1f2f7", text: "#0d6277" },
  "returned transfers": { dot: "#1789a6", tint: "#e1f2f7", text: "#0d6277" },
  "cash withdrawals": { dot: "#d0621b", tint: "#fdeadc", text: "#9a430c" },
}

/** Further hues, in order, for the other categories ("next free hue"). */
const MORE: CategoryTone[] = [
  { dot: "#8a5a2b", tint: "#f5ece2", text: "#5e3c1a" },
  { dot: "#2e7d9a", tint: "#e2f0f5", text: "#1b566b" },
  { dot: "#a03f9a", tint: "#f6e6f5", text: "#712b6d" },
  { dot: "#5d7a1f", tint: "#eef3e0", text: "#3f5414" },
  { dot: "#b5543a", tint: "#fae9e3", text: "#7d3725" },
  { dot: "#3f6e5c", tint: "#e4efea", text: "#294a3d" },
  { dot: "#6b5bb5", tint: "#ece9f8", text: "#47398a" },
  { dot: "#9a7b10", tint: "#f7f0d9", text: "#66510a" },
  { dot: "#2a7fbf", tint: "#e3effa", text: "#1a5784" },
  { dot: "#b0476f", tint: "#f8e5ed", text: "#7c2d4c" },
  { dot: "#4f7f3a", tint: "#e7f1e2", text: "#345525" },
  { dot: "#7a6a58", tint: "#efebe6", text: "#524638" },
]

export const UNCATEGORIZED: CategoryTone = {
  dot: "#d99a2b",
  tint: "#fdf0d5",
  text: "#8a5300",
}

const hash = (value: string) =>
  [...value].reduce((sum, c) => (sum * 31 + c.charCodeAt(0)) >>> 0, 7)

/** A category's colours: the spec's for the named ones, the person's chosen dot when set, else a stable free hue. */
export function categoryTone(name: string, chosen?: string): CategoryTone {
  const key = name.trim().toLowerCase()
  if (!key || key === "uncategorized") return UNCATEGORIZED
  if (SPEC[key]) return SPEC[key]
  const base = MORE[hash(key) % MORE.length]
  // The library's default purple means "not chosen"; anything else is the person's colour.
  if (chosen && chosen.toLowerCase() !== "#8060a9")
    return { dot: chosen, tint: `${chosen}1f`, text: base.text }
  return base
}

export function minorToNumber(minor: bigint, currency: string) {
  const exponent = currencyMinorUnits(currency) ?? 2
  return Number(minor) / 10 ** exponent
}

/** 89.19 m, 752 k, 825: the headline form. Exact figures stay in titles and the totals panel. */
export function compactMoney(value: number) {
  const size = Math.abs(value)
  const [divisor, suffix] =
    size >= 1e9 ? [1e9, " bn"] : size >= 1e6 ? [1e6, " m"] : size >= 1e3 ? [1e3, " k"] : [1, ""]
  const digits = divisor === 1 ? 0 : size / divisor >= 100 ? 1 : 2
  return `${(value / divisor).toLocaleString("en", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}${suffix}`
}

export interface MoneyGroup {
  key: string
  label: string
  count: number
  credit: bigint
  debit: bigint
  rows: LedgerTransaction[]
}

const amount = (row: LedgerTransaction) => {
  try {
    return BigInt(row.amount_minor)
  } catch {
    return 0n
  }
}

export function groupMoney(
  rows: LedgerTransaction[],
  keyOf: (row: LedgerTransaction) => [string, string]
): MoneyGroup[] {
  const groups = new Map<string, MoneyGroup>()
  for (const row of rows) {
    const [key, label] = keyOf(row)
    let group = groups.get(key)
    if (!group) {
      group = { key, label, count: 0, credit: 0n, debit: 0n, rows: [] }
      groups.set(key, group)
    }
    group.count += 1
    group.rows.push(row)
    if (row.direction === "credit") group.credit += amount(row)
    else group.debit += amount(row)
  }
  return [...groups.values()].sort((a, b) => {
    const diff = b.credit + b.debit - (a.credit + a.debit)
    return diff > 0n ? 1 : diff < 0n ? -1 : a.label.localeCompare(b.label)
  })
}

/** Months from the first to the last dated payment, including the empty ones (gaps are shown, never skipped). */
export function monthSeries(rows: LedgerTransaction[]) {
  const byMonth = groupMoney(
    rows.filter((row) => paymentDay(row)),
    (row) => {
      const month = paymentDay(row)!.slice(0, 7)
      return [month, month]
    }
  )
  const known = new Map(byMonth.map((group) => [group.key, group]))
  const keys = [...known.keys()].sort()
  if (!keys.length) return []
  const series: { month: string; group?: MoneyGroup }[] = []
  let [year, month] = keys[0].split("-").map(Number)
  const last = keys[keys.length - 1]
  for (let guard = 0; guard < 600; guard += 1) {
    const key = `${year}-${String(month).padStart(2, "0")}`
    series.push({ month: key, group: known.get(key) })
    if (key === last) break
    month += 1
    if (month > 12) {
      month = 1
      year += 1
    }
  }
  return series
}
